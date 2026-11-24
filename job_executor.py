import json
import threading
from pathlib import Path
from typing import Any, Optional

from api_client import ApiClient
from rocketbot_runner import RocketbotRunner


class JobExecutor:
    SUPPORTED_JOB_TYPES = {"CARGAR_NUEVO_TOKEN"}
    METEOSTREAM_STAGE_TYPES = {
        "OBTENER_RENOVAR_TOKEN",
        "EXTRAER_CLIMA",
        "EXTRAER_SISMOS",
        "GENERAR_EXCEL",
        "SUBIR_GOOGLE_DRIVE",
        "ENVIAR_FASTAPI",
        "ENVIAR_CORREO",
        "RECUPERAR_ETAPA",
    }

    def __init__(self, settings, api: ApiClient, logger) -> None:
        self.settings = settings
        self.api = api
        self.logger = logger
        self.lock = threading.Lock()
        self.runner: Optional[RocketbotRunner] = None

        self.runner = RocketbotRunner(
            executable=self.settings.rocketbot_executable,
            database=self.settings.robot_database,
            robot_name=self.settings.robot_name,
            log_dir=self.settings.rocketbot_log_dir,
            timeout_seconds=self.settings.execution_timeout_seconds,
            logger=self.logger,
        )

    def load_state(self) -> dict[str, Any]:
        path: Path = self.settings.state_file
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            self.logger.error("No fue posible leer el estado local: %s", exc)
            return {}

    def save_state(self, state: dict[str, Any]) -> None:
        temporary = self.settings.state_file.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.settings.state_file)

    def stop(self) -> None:
        if self.runner is not None:
            self.runner.stop()
        self.save_state(
            {
                "status": "AGENTE_DETENIDO",
                "detail": "Detención solicitada de forma segura",
            }
        )

    def check_restart_state(self) -> None:
        state = self.load_state()
        job_id = state.get("job_id")
        status = state.get("status")
        if job_id:
            backend_job = self.api.consultar_trabajo(job_id)
            if backend_job is not None:
                backend_status = backend_job.get("estado")
                if backend_status in {
                    "COMPLETADO",
                    "EJECUCION_COMPLETADA",
                    "EJECUCION_ERROR",
                    "ESTADO_NO_CONFIRMADO",
                    "ERROR",
                }:
                    self.logger.info(
                        "Al reiniciar se confirmó trabajo %s en estado %s",
                        job_id,
                        backend_status,
                    )
                    state["status"] = backend_status
                    self.save_state(state)
                    return
                if backend_status in {"PENDIENTE", "RECLAMADO", "EN_EJECUCION"}:
                    self.logger.warning(
                        "Al reiniciar el trabajo %s está en estado %s",
                        job_id,
                        backend_status,
                    )
        backend = self.api.consultar_estado()
        if backend is not None:
            trabajo = backend.get("trabajo")
            if trabajo and trabajo.get("estado") in {
                "COMPLETADO",
                "EJECUCION_COMPLETADA",
            }:
                self.logger.info(
                    "Al reiniciar se confirmó trabajo completado %s",
                    trabajo.get("id"),
                )
                state["status"] = "COMPLETADO"
                self.save_state(state)
                return

        if job_id and status in {"EJECUCION_INICIADA", "ejecutando"}:
            self.logger.warning(
                "Inconsistencia tras reinicio: el trabajo %s quedó como %s",
                job_id,
                status,
            )
            self.api.finalizar(
                job_id,
                "ESTADO_NO_CONFIRMADO",
                "El agente se reinició antes de confirmar el resultado",
            )
            state["status"] = "ESTADO_NO_CONFIRMADO"
            state["detail"] = "Reinicio previo a confirmación"
            self.save_state(state)

    def inspect_dry_run(self) -> dict[str, Any]:
        check = self.runner.dry_run_check()
        state = (
            "ROBOT_PREPARADO"
            if check["configuracion_ok"]
            else "ROBOT_NO_CONFIRMADO"
        )
        detail = (
            "DRY_RUN: mecanismo oficial encontrado; ejecutable, base y "
            "nombre comprobados; Clima no fue iniciado"
            if check["configuracion_ok"]
            else "DRY_RUN: ejecutable, base o nombre de robot no disponible"
        )
        self.logger.info(
            "DRY_RUN runner=%s",
            check,
        )
        self.logger.info("DRY_RUN: no se ejecutó el robot")
        self.save_state(
            {
                "status": state,
                "robot_name": self.settings.robot_name,
                "dry_run": True,
                "detail": detail,
                "runner": check,
            }
        )
        return {
            "estado": state,
            "detalle": detail,
            "robot_seleccionado": check["configuracion_ok"],
            "runner": check,
        }

    def dry_run_type_tests(self) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        types = [
            "CARGAR_NUEVO_TOKEN",
            "OBTENER_RENOVAR_TOKEN",
            "EXTRAER_CLIMA",
            "EXTRAER_SISMOS",
            "GENERAR_EXCEL",
            "SUBIR_GOOGLE_DRIVE",
            "ENVIAR_FASTAPI",
            "ENVIAR_CORREO",
            "RECUPERAR_ETAPA",
        ]
        for tipo in types:
            if tipo in self.SUPPORTED_JOB_TYPES:
                results[tipo] = {
                    "resultado": "COMPATIBLE_DRY_RUN",
                    "detalle": "Tipo soportado; no se inicia Rocketbot",
                }
            elif tipo in self.METEOSTREAM_STAGE_TYPES:
                results[tipo] = {
                    "resultado": "NO_SOPORTADO",
                    "detalle": (
                        "Nombre de etapa conocido por el inventario, pero no "
                        "hay ejecutor aislado ni contrato implementado"
                    ),
                }
            else:
                results[tipo] = {
                    "resultado": "NO_SOPORTADO",
                    "detalle": "Tipo desconocido",
                }
        return results

    def execute_job(self, job: dict[str, Any]) -> None:
        if not self.lock.acquire(blocking=False):
            self.logger.warning("Ya existe un trabajo local en ejecución")
            return
        try:
            job_id = str(job.get("id") or job.get("trabajo_id") or "")
            if not job_id:
                self.logger.warning("Trabajo sin identificador: %r", job)
                return

            if self.settings.monitor_only:
                tipo = str(job.get("tipo") or "DESCONOCIDO")
                etapa = str(
                    job.get("etapa_actual")
                    or job.get("etapa_fallida")
                    or "SIN_ETAPA"
                )
                detail = (
                    "Modo supervisor de solo monitoreo: trabajo "
                    f"{job_id} no ejecutado. tipo={tipo}; "
                    f"etapa={etapa}; intervención manual requerida"
                )
                self.logger.warning(
                    "ALERTA | trabajo_id=%s | tipo=%s | etapa=%s | estado=REQUIERE_INTERVENCION",
                    job_id,
                    tipo,
                    etapa,
                )
                self.api.finalizar(
                    job_id,
                    "ESTADO_NO_CONFIRMADO",
                    detail,
                )
                self.save_state(
                    {
                        "job_id": job_id,
                        "status": "REQUIERE_INTERVENCION",
                        "tipo": tipo,
                        "etapa": etapa,
                        "detail": detail,
                        "monitor_only": True,
                    }
                )
                return

            tipo = str(job.get("tipo") or "CARGAR_NUEVO_TOKEN")
            if tipo not in self.SUPPORTED_JOB_TYPES:
                detail = f"Tipo de trabajo no soportado: {tipo}"
                self.logger.error(detail)
                self.api.registrar_error(job_id, detail)
                self.save_state(
                    {
                        "job_id": job_id,
                        "status": "TIPO_NO_SOPORTADO",
                        "detail": detail,
                    }
                )
                return

            etapa_fallida = str(job.get("etapa_fallida") or "").strip()
            if etapa_fallida:
                completadas_raw = job.get("etapas_completadas") or "[]"
                try:
                    completadas = json.loads(completadas_raw)
                except json.JSONDecodeError:
                    completadas = []
                if etapa_fallida in completadas:
                    detail = (
                        f"Recuperación rechazada: la etapa {etapa_fallida} "
                        "ya figura como completada"
                    )
                    self.logger.error(detail)
                    self.api.registrar_error(job_id, detail)
                    return
                self.logger.info(
                    "DRY_RUN recuperación de etapa %s; etapas completadas=%s",
                    etapa_fallida,
                    completadas,
                )

            prior = self.load_state()
            if prior.get("job_id") == job_id:
                self.logger.warning(
                    "Trabajo %s ya tiene registro local; no se repetirá",
                    job_id,
                )
                return

            if self.settings.dry_run:
                self.api.iniciar(job_id)
                self.save_state(
                    {
                        "job_id": job_id,
                        "status": "EJECUCION_INICIADA",
                        "robot_name": self.settings.robot_name,
                        "dry_run": True,
                    }
                )
                result = self.inspect_dry_run()
                self.api.finalizar(
                    job_id,
                    result["estado"],
                    result["detalle"],
                )
                return

            if not self.settings.allowed_real_click:
                detail = (
                    "Ejecución real bloqueada: ALLOW_REAL_EXECUTION "
                    "no está habilitado"
                )
                self.logger.warning(detail)
                self.api.finalizar(job_id, "ESTADO_NO_CONFIRMADO", detail)
                return

            check = self.runner.dry_run_check()
            if not check["configuracion_ok"]:
                detail = "Configuración Rocketbot incompleta"
                self.api.finalizar(job_id, "ESTADO_NO_CONFIRMADO", detail)
                return

            started, detail = self.runner.start()
            if not started:
                self.api.finalizar(job_id, "ESTADO_NO_CONFIRMADO", detail)
                return

            self.api.iniciar(job_id)
            self.save_state(
                {
                    "job_id": job_id,
                    "status": "EJECUCION_INICIADA",
                    "robot_name": self.settings.robot_name,
                }
            )
            estado, detail = self.runner.wait_for_result()
            self.api.finalizar(job_id, estado, detail)
            self.save_state(
                {
                    "job_id": job_id,
                    "status": estado,
                    "detail": detail,
                }
            )
        finally:
            self.lock.release()
