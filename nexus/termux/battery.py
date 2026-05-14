"""Battery status dataclass for Termux."""

from dataclasses import dataclass


@dataclass
class BatteryStatus:
    health: str = "unknown"
    percentage: int = 0
    plugged: str = "unknown"  # "AC", "USB", "wireless", or "none"
    temperature: float = 0.0
    voltage: int = 0
    mode: str = "unknown"  # "unspecified", "trickle", "normal", "full"

    @property
    def is_charging(self) -> bool:
        return self.plugged not in ("none", "unknown")

    @property
    def icon(self) -> str:
        pct = self.percentage
        if self.is_charging:
            return "⚡"
        if pct > 80:
            return "🟢"
        if pct > 50:
            return "🟡"
        if pct > 20:
            return "🟠"
        return "🔴"

    def format(self) -> str:
        charging_str = "🔌 charging" if self.is_charging else "🔋 on battery"
        return f"{self.icon} {self.percentage}% {charging_str}"

    @classmethod
    def from_dict(cls, data: dict) -> "BatteryStatus":
        return cls(
            health=data.get("health", "unknown"),
            percentage=data.get("percentage", 0),
            plugged=data.get("plugged", "unknown"),
            temperature=data.get("temperature", 0.0),
            voltage=data.get("voltage", 0),
            mode=data.get("mode", "unknown"),
        )
