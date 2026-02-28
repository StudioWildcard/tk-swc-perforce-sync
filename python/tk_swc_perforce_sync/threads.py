import threading
from sgtk.platform.qt import QtCore

from time import sleep
import sgtk
logger = sgtk.platform.get_logger(__name__)


class SyncThread(threading.Thread):
    def __init__(self, p4=None, file_name=None):
        super().__init__()
        self.p4 = p4
        self.file_name = file_name

    def sync_file(self):
        logger.debug("--------->>>>>>  Syncing file: {}".format(self.file_name))
        p4_result = self.p4.run("sync", "-f", self.file_name + "#head")
        logger.debug("--------->>>>>>  Syncing result: {}".format(p4_result))

    def run(self):
        self.sync_file()


class FileSyncThread(threading.Thread):
    def __init__(self, p4=None, file_queue=None):
        super().__init__()
        self.p4 = p4
        self.file_queue = file_queue

    def run(self):
        while not self.file_queue.empty():
            file_path = self.file_queue.get()
            self.sync_file(file_path)

    def sync_file(self, file_path):
        logger.debug("--------->>>>>>  Syncing file: {}".format(file_path))
        p4_result = self.p4.run("sync", "-f", file_path + "#head")
        logger.debug("--------->>>>>>  Syncing result: {}".format(p4_result))
