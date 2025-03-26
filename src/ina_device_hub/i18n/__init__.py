from ina_device_hub.i18n import i18n_en, i18n_ja
from ina_device_hub.setting import setting

language = setting().get("language")


class I18n:
    def __init__(self):
        self.language = language
        self.default_dictionary = i18n_en.dictionary

    def get_dictionary(self, lang=language):
        ret = self.default_dictionary
        if lang == "ja":
            ret.update(i18n_ja.dictionary)

        return ret


__instance = None


def i18n():
    global __instance
    if not __instance:
        __instance = I18n()
    return __instance
