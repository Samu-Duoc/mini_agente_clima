from typing import Any, Optional

import requests


class ApiClient:
    def __init__(self, base_url: str, api_key: str, agent_id: str, logger) -> None:
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-AGENT-API-KEY": api_key,
            }
        )

    def _post(self, path: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not self.base_url:
            self.logger.warning("API_BASE_URL no está configurada")
            return None
        url = f"{self.base_url}{path}"
        try:
            response = self.session.post(url, json=payload, timeout=10)
            if response.status_code == 404:
                self.logger.warning("FastAPI no implementa el endpoint %s", path)
                return None
            response.raise_for_status()
            if not response.content:
                return {}
            data = response.json()
            return data if isinstance(data, dict) else {"data": data}
        except requests.RequestException as exc:
            self.logger.warning("API desconectada o inaccesible en %s: %s", url, exc)
            return None

    def _get(self, path: str, params: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not self.base_url:
            return None
        url = f"{self.base_url}{path}"
        try:
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {"data": data}
        except requests.RequestException as exc:
            self.logger.warning("API desconectada o inaccesible en %s: %s", url, exc)
            return None

    def heartbeat(self) -> Optional[dict[str, Any]]:
        return self._post(
            "/api/robot/agente/heartbeat",
            {"agent_id": self.agent_id, "estado": "activo"},
        )

    def siguiente(self) -> Optional[dict[str, Any]]:
        return self._post(
            "/api/robot/agente/siguiente",
            {"agent_id": self.agent_id, "estado": "activo"},
        )

    def consultar_estado(self) -> Optional[dict[str, Any]]:
        return self._get(
            "/api/robot/agente/estado",
            {"agente_id": self.agent_id},
        )

    def consultar_trabajo(self, job_id: str) -> Optional[dict[str, Any]]:
        return self._get(
            f"/api/robot/trabajos/{job_id}",
            {},
        )

    def report_state(self, estado: str, detalle: Optional[str] = None,
                     job_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        payload: dict[str, Any] = {"agent_id": self.agent_id, "estado": estado}
        if detalle:
            payload["detalle"] = detalle
        if job_id:
            payload["trabajo_id"] = job_id

        if job_id:
            return self._post(f"/api/robot/trabajos/{job_id}/finalizar", payload)
        return self.heartbeat()

    def iniciar(self, job_id: str) -> Optional[dict[str, Any]]:
        return self._post(
            f"/api/robot/trabajos/{job_id}/iniciar",
            {
                "agent_id": self.agent_id,
                "estado": "EJECUCION_INICIADA",
                "detalle": "Inicio registrado por el mini agente",
            },
        )

    def finalizar(self, job_id: str, estado: str,
                  detalle: Optional[str] = None) -> Optional[dict[str, Any]]:
        payload: dict[str, Any] = {
            "agent_id": self.agent_id,
            "estado": estado,
        }
        if detalle:
            payload["detalle"] = detalle
        return self._post(f"/api/robot/trabajos/{job_id}/finalizar", payload)

    def registrar_error(self, job_id: str,
                        detalle: Optional[str] = None) -> Optional[dict[str, Any]]:
        payload: dict[str, Any] = {
            "agent_id": self.agent_id,
            "estado": "EJECUCION_ERROR",
        }
        if detalle:
            payload["detalle"] = detalle
        return self._post(f"/api/robot/trabajos/{job_id}/error", payload)

    def solicitar_trabajo(self, clave_solicitud: str,
                          tipo: str = "CARGAR_NUEVO_TOKEN",
                          robot: str = "Clima",
                          origen: str = "dashboard",
                          intentos_maximos: int = 3,
                          minutos_expiracion: int = 15) -> Optional[dict[str, Any]]:
        return self._post(
            "/api/robot/trabajos/solicitar",
            {
                "clave_solicitud": clave_solicitud,
                "tipo": tipo,
                "robot": robot,
                "origen": origen,
                "intentos_maximos": intentos_maximos,
                "minutos_expiracion": minutos_expiracion,
            },
        )

    def registrar_etapa(
        self,
        job_id: str,
        etapa: str,
        estado: str,
        detalle: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        payload: dict[str, Any] = {
            "agent_id": self.agent_id,
            "etapa": etapa,
            "estado": estado,
        }
        if detalle:
            payload["detalle"] = detalle
        return self._post(
            f"/api/robot/trabajos/{job_id}/etapa",
            payload,
        )
