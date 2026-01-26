from PyQt6.QtCore import QSettings


class Settings:
    """Application settings using Qt's QSettings.

    Stores config in ~/.config/postured/postured.conf (on Linux).
    """

    DEFAULTS = {
        'sensitivity': 0.85,
        'camera_index': 0,
        'lock_when_away': False,
        'good_posture_y': 0.4,
        'bad_posture_y': 0.6,
        'is_calibrated': False,
    }

    def __init__(self):
        self._settings = QSettings('postured', 'postured')

    @property
    def sensitivity(self) -> float:
        value = float(self._settings.value('sensitivity', self.DEFAULTS['sensitivity']))
        return max(0.1, min(1.0, value))

    @sensitivity.setter
    def sensitivity(self, value: float):
        self._settings.setValue('sensitivity', value)

    @property
    def camera_index(self) -> int:
        value = int(self._settings.value('camera_index', self.DEFAULTS['camera_index']))
        return max(0, value)

    @camera_index.setter
    def camera_index(self, value: int):
        self._settings.setValue('camera_index', value)

    @property
    def lock_when_away(self) -> bool:
        return self._settings.value('lock_when_away', self.DEFAULTS['lock_when_away'], type=bool)

    @lock_when_away.setter
    def lock_when_away(self, value: bool):
        self._settings.setValue('lock_when_away', value)

    @property
    def good_posture_y(self) -> float:
        value = float(self._settings.value('good_posture_y', self.DEFAULTS['good_posture_y']))
        return max(0.0, min(1.0, value))

    @good_posture_y.setter
    def good_posture_y(self, value: float):
        self._settings.setValue('good_posture_y', value)

    @property
    def bad_posture_y(self) -> float:
        value = float(self._settings.value('bad_posture_y', self.DEFAULTS['bad_posture_y']))
        return max(0.0, min(1.0, value))

    @bad_posture_y.setter
    def bad_posture_y(self, value: float):
        self._settings.setValue('bad_posture_y', value)

    @property
    def is_calibrated(self) -> bool:
        return self._settings.value('is_calibrated', self.DEFAULTS['is_calibrated'], type=bool)

    @is_calibrated.setter
    def is_calibrated(self, value: bool):
        self._settings.setValue('is_calibrated', value)

    def sync(self):
        """Force write settings to disk."""
        self._settings.sync()
