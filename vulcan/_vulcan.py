from __future__ import unicode_literals

import platform
from datetime import datetime
from operator import itemgetter

import requests
from related import to_model

from ._api import Api
from ._dictionaries import Dictionaries
from ._exam import Exam
from ._grade import Grade
from ._homework import Homework
from ._lesson import Lesson
from ._student import Student
from ._utils import log, uuid, now, get_base_url, sort_and_filter_date


class Vulcan(Api):
    """
    Loguje się do dzienniczka za pomocą wygenerowanego certyfikatu

    Args:
        certificate (:class:`dict`): Certyfikat wygenerowany za pomocą :func:`vulcan.Vulcan.register`
    """

    def __init__(self, certificate, logging_level=None):
        super(Vulcan, self).__init__(certificate)
        self._dict = None

        if logging_level:
            Vulcan.set_logging_level(logging_level)

        self.students = self.get_students()
        self.set_student(next(self.students))

    @staticmethod
    def set_logging_level(logging_level):
        """
        Ustawia poziom logowania

        Args:
            logging_level (:class:`int`): Poziom logowania z modułu :module:`logging`
        """

        log.setLevel(logging_level)

    @staticmethod
    def register(token, symbol, pin):
        """
        Rejestruje API jako nowe urządzenie mobilne

        Args:
            token (:class:`str`): Token
            symbol (:class:`str`): Symbol/Nazwa instancji
            pin (:class:`str`): Kod PIN

        Returns:
            :class:`dict`: Certyfikat
        """

        token = str(token).upper()
        symbol = str(symbol).lower()
        pin = str(pin)

        data = {
            "PIN": pin,
            "TokenKey": token,
            "AppVersion": Vulcan.APP_VERSION,
            "DeviceId": uuid(),
            "DeviceName": "Vulcan API",
            "DeviceNameUser": "",
            "DeviceDescription": "",
            "DeviceSystemType": "Python",
            "DeviceSystemVersion": platform.python_version(),
            "RemoteMobileTimeKey": now() + 1,
            "TimeKey": now(),
            "RequestId": uuid(),
            "RemoteMobileAppVersion": Vulcan.APP_VERSION,
            "RemoteMobileAppName": Vulcan.APP_NAME,
        }

        headers = {
            "RequestMobileType": "RegisterDevice",
            "User-Agent": "MobileUserAgent",
        }

        base_url = get_base_url(token)
        url = "{}/{}/mobile-api/Uczen.v3.UczenStart/Certyfikat".format(base_url, symbol)

        log.info("Registering...")

        r = requests.post(url, json=data, headers=headers)
        j = r.json()
        log.debug(j)

        cert = j["TokenCert"]
        log.info("Registered successfully!")

        return cert

    def _get_dict(self):
        j = self._post("Uczen/Slowniki")
        return to_model(Dictionaries, j.get("Data"))

    def get_students(self):
        """
        Zwraca listę wszystkich uczniów należących do użytkownika

        Returns:
            :class:`list`: Listę uczniów
        """

        j = self._post(self._base_url + "UczenStart/ListaUczniow")

        for student in j.get("Data", []):
            yield to_model(Student, Student.format_json(student))

    def set_student(self, student):
        """
        Ustawia domyślnego ucznia

        Args:
            uczen (:class:`vulcan.Student`): Jeden z uczniów zwróconych przez :func:`vulcan.Vulcan.uczniowie`
        """

        self.student = student
        self._full_url = self._url + student.school.symbol + "/mobile-api/Uczen.v3."
        self._dict = self._get_dict()

    def get_grades(self):
        """
        Pobiera oceny cząstkowe

        Returns:
            :class:`list`: Listę ocen cząstkowych
        """

        j = self._post("Uczen/Oceny")

        for grade in j.get("Data", []):
            grade["teacher"] = self._dict.get_teacher(grade["IdPracownikD"])
            grade["subject"] = self._dict.get_subject(grade["IdPrzedmiot"])
            grade["category"] = self._dict.get_category(grade["IdKategoria"])

            yield to_model(Grade, grade)

    def get_lessons(self, date=None):
        """
        Pobiera plan lekcji z danego dnia

        Args:
            date (:class:`datetime.date` or :class:`datetime.datetime`): Dzień z którego pobrać plan
                lekcji, jeśli puste pobiera z aktualnego dnia

        Returns:
            :class:`list`: Listę lekcji
        """

        if not date:
            date = datetime.now()
        date_str = date.strftime("%Y-%m-%d")

        data = {"DataPoczatkowa": date_str, "DataKoncowa": date_str}

        j = self._post("Uczen/PlanLekcjiZeZmianami", json=data)

        lessons = sorted(j.get("Data", []), key=itemgetter("NumerLekcji"))
        lessons = list(filter(lambda x: x["DzienTekst"] == date_str, lessons))

        for lesson in lessons:
            lesson["time"] = self._dict.get_lesson_time(lesson["IdPoraLekcji"])
            lesson["teacher"] = self._dict.get_teacher(lesson["IdPracownik"])
            lesson["subject"] = self._dict.get_subject(lesson["IdPrzedmiot"])

            yield to_model(Lesson, lesson)

    def _get_exams(self, date, model):
        if not date:
            date = datetime.now()
        date_str = date.strftime("%Y-%m-%d")

        data = {"DataPoczatkowa": date_str, "DataKoncowa": date_str}

        if isinstance(model, Exam):
            endpoint = "Uczen/Sprawdziany"
        elif isinstance(model, Homework):
            endpoint = "Uczen/ZadaniaDomowe"
        else:
            return

        j = self._post(endpoint, json=data)

        exams = sort_and_filter_date(j.get("Data", []), date_str)

        for exam in exams:
            exam["teacher"] = self._dict.get_teacher(exam["IdPracownik"])
            exam["subject"] = self._dict.get_subject(exam["IdPrzedmiot"])

            yield to_model(model, exam)

    def get_exams(self, date=None):
        """
        Pobiera sprawdziany z danego dnia

        Args:
            date (:class:`datetime.date` or :class:`datetime.datetime`): Dzień z którego pobrać
                sprawdziany, jeśli puste pobiera z aktualnego dnia

        Returns:
            :class:`list`: Listę sprawdzianów
        """
        return self._get_exams(date=date, model=Exam)

    def get_homework(self, date=None):
        """
        Pobiera zadania domowe z danego dnia

        Args:
            date (:class:`datetime.date` or :class:`datetime.datetime`): Dzień z którego pobrać
                zadania domowe, jeśli puste pobiera z aktualnego dnia

        Returns:
            :class:`list`: Listę zadań domowych
        """
        return self._get_exams(date=date, model=Homework)
