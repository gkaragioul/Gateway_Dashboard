import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    base_dir: Path
    config_path: Path
    log_dir: Path
    data_dir: Path
    write_operations_enabled: bool = False

    @classmethod
    def from_env(cls) -> "AppSettings":
        base = os.environ.get("PCDD_HOME")
        if base:
            base_dir = Path(base)
        elif os.name == "nt":
            base_dir = Path("G:/Tools/GatewayDashboard")
        else:
            base_dir = Path.home() / ".gateway-dashboard"

        config_dir = Path(os.environ.get("PCDD_CONFIG_DIR", base_dir / "config"))
        log_dir = Path(os.environ.get("PCDD_LOG_DIR", base_dir / "logs"))
        data_dir = Path(os.environ.get("PCDD_DATA_DIR", base_dir / "data"))
        return cls(
            base_dir=base_dir,
            config_path=config_dir / "config.json",
            log_dir=log_dir,
            data_dir=data_dir,
            write_operations_enabled=os.environ.get("PCDD_ENABLE_WRITES") == "1",
        )

    def ensure_dirs(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
