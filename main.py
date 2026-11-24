import signal
import threading
import os
import ctypes
from pathlib import Path

from api_client import ApiClient
from job_executor import JobExecutor
from logger import build_logger
from settings import BASE_DIR, Settings


settings = Settings.from_environment()
logger = build_logger(BASE_DIR)
api = ApiClient(
    settings.api_base_url,
    settings.agent_api_key,
    settings.agent_id,
    logger,
)
executor = JobExecutor(settings, api, logger)
stop_event = threading.Event()
instance_lock = None
INSTANCE_LOCK_PATH = Path(BASE_DIR) / ".agent.lock"


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        process = ctypes.windll.kernel32.OpenProcess(
            0x1000,
            False,
            pid,
        )
        if not process:
            return False
        ctypes.windll.kernel32.CloseHandle(process)
        return True
    except (AttributeError, OSError):
        return False


def acquire_instance_lock() -> bool:
    global instance_lock
    lock_path = INSTANCE_LOCK_PATH
    try:
        if lock_path.exists():
            text = lock_path.read_text(encoding="ascii").strip()
            if text.isdigit() and process_exists(int(text)):
                return False
        instance_lock = lock_path.open("x")
        instance_lock.write(str(os.getpid()))
        instance_lock.flush()
        return True
    except FileExistsError:
        try:
            text = lock_path.read_text(encoding="ascii").strip()
            if text.isdigit() and process_exists(int(text)):
                return False
            lock_path.unlink(missing_ok=True)
            instance_lock = lock_path.open("x")
            instance_lock.write(str(os.getpid()))
            instance_lock.flush()
            return True
        except (OSError, PermissionError):
            return False
    except (OSError, PermissionError):
        return False


def release_instance_lock() -> None:
    global instance_lock
    if instance_lock is not None:
        try:
            instance_lock.close()
        except OSError:
            pass
        instance_lock = None
    try:
        text = INSTANCE_LOCK_PATH.read_text(encoding="ascii").strip()
        if text == str(os.getpid()):
            INSTANCE_LOCK_PATH.unlink(missing_ok=True)
    except (OSError, PermissionError):
        pass


def handle_stop(_signum=None, _frame=None) -> None:
    stop_event.set()
    executor.stop()


signal.signal(signal.SIGINT, handle_stop)
signal.signal(signal.SIGTERM, handle_stop)


def heartbeat_loop() -> None:
    while not stop_event.wait(settings.heartbeat_seconds):
        api.heartbeat()


def main() -> None:
    if not acquire_instance_lock():
        logger.error("Ya existe otra instancia del mismo mini agente")
        return

    logger.info(
        "Agente iniciado | agent_id=%s | dry_run=%s",
        settings.agent_id,
        settings.dry_run,
    )
    if not settings.api_base_url:
        logger.warning("API_BASE_URL no está configurada")
    executor.check_restart_state()
    api.report_state("AGENTE_CONECTADO")

    if settings.dry_run:
        dry_run_result = executor.inspect_dry_run()
        logger.info(
            "DRY_RUN iniciado | estado=%s",
            dry_run_result["estado"],
        )

    heartbeat = threading.Thread(target=heartbeat_loop, daemon=True)
    heartbeat.start()

    while not stop_event.is_set():
        try:
            response = api.siguiente()
            if response:
                jobs = response.get("trabajos")
                if isinstance(jobs, list):
                    for job in jobs:
                        if stop_event.is_set():
                            break
                        executor.execute_job(job)
                else:
                    claimed_job = response.get("trabajo")
                    if isinstance(claimed_job, dict):
                        executor.execute_job(claimed_job)
                    elif response.get("id") or response.get("trabajo_id"):
                        executor.execute_job(response)
        except Exception as exc:
            logger.exception("Error controlado en el ciclo principal: %s", exc)
        stop_event.wait(settings.poll_seconds)

    logger.info("Agente detenido")
    release_instance_lock()


if __name__ == "__main__":
    main()
