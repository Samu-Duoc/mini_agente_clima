import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional


class RocketbotRunner:
    def __init__(
        self,
        executable: str,
        database: str,
        robot_name: str,
        log_dir: str,
        timeout_seconds: int,
        logger,
    ) -> None:
        self.executable = Path(executable)
        self.database = Path(database)
        self.robot_name = robot_name
        self.log_dir = Path(log_dir)
        self.timeout_seconds = timeout_seconds
        self.logger = logger
        self.lock = threading.Lock()
        self.process: Optional[subprocess.Popen] = None

    def dry_run_check(self) -> dict:
        return {
            "configuracion_ok": (
                self.executable.is_file()
                and self.database.is_file()
                and bool(self.robot_name)
            ),
            "ejecutable": str(self.executable),
            "base_datos": str(self.database),
            "robot": self.robot_name,
            "mecanismo": (
                "-db=<ruta_robot.db> -start=<nombre_robot>"
            ),
            "opcion_sin_logs_verificada": "--nodebug",
            "resultado": (
                "MECANISMO_OFICIAL_ENCONTRADO_NO_PROBADO"
                if self.executable.is_file() and self.database.is_file()
                else "CONFIGURACION_INCOMPLETA"
            ),
        }

    def build_command(self) -> list[str]:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        return [
            str(self.executable),
            f"-db={str(self.database)}",
            f"-start={self.robot_name}",
            "--nodebug",
            f"--log={str(self.log_dir)}",
        ]

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self) -> tuple[bool, str]:
        if not self.lock.acquire(blocking=False):
            return False, "Otro proceso Rocketbot creado por el agente está activo"
        try:
            if self.is_running():
                return False, "Ya existe una ejecución Rocketbot activa"
            if not self.executable.is_file():
                self.lock.release()
                return False, f"Ejecutable no encontrado: {self.executable}"
            if not self.database.is_file():
                self.lock.release()
                return False, f"Base de datos no encontrada: {self.database}"

            command = self.build_command()
            startupinfo = None
            creationflags = 0
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW

            self.logger.info(
                "Lanzando Rocketbot mediante mecanismo oficial; robot=%s db=%s",
                self.robot_name,
                self.database,
            )
            self.process = subprocess.Popen(
                command,
                cwd=str(self.executable.parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )
            threading.Thread(
                target=self._release_lock_when_process_exits,
                daemon=True,
            ).start()
            return True, f"Proceso iniciado con PID {self.process.pid}"
        except (OSError, subprocess.SubprocessError) as exc:
            self.logger.exception("No fue posible lanzar Rocketbot: %s", exc)
            if self.lock.locked():
                self.lock.release()
            return False, f"No fue posible iniciar el proceso: {exc}"

    def _release_lock_when_process_exits(self) -> None:
        process = self.process
        if process is None:
            return
        while process.poll() is None:
            time.sleep(1)
        if self.lock.locked():
            self.lock.release()

    def wait_for_result(self) -> tuple[str, str]:
        if self.process is None:
            return "ESTADO_NO_CONFIRMADO", "No existe proceso para supervisar"
        try:
            return_code = self.process.wait(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            return "ESTADO_NO_CONFIRMADO", (
                f"Timeout de {self.timeout_seconds}s sin confirmación suficiente"
            )

        if return_code != 0:
            return "EJECUCION_ERROR", (
                f"Rocketbot terminó con código de salida {return_code}"
            )

        return "ESTADO_NO_CONFIRMADO", (
            "El proceso terminó con código 0, pero el resultado de "
            "Clima no fue confirmado por una salida real verificable"
        )

    def stop(self) -> None:
        if self.process is not None and self.is_running():
            self.process.terminate()
