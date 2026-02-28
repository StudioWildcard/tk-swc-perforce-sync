import sys
from sgtk.platform.qt import QtCore
for name, cls in QtCore.__dict__.items():
    if isinstance(cls, type): globals()[name] = cls

from sgtk.platform.qt import QtGui
for name, cls in QtGui.__dict__.items():
    if isinstance(cls, type): globals()[name] = cls

import sgtk

logger = sgtk.platform.get_logger(__name__)

class PublishedFileSPerforce(QTreeView):
    def __init__(self, parent=None, sg_data=None, fstat_dict=None, p4=None):
        super().__init__(parent)

        self.sg_data = sg_data
        self.fstat_dict = fstat_dict
        self.p4 = p4
        self.app = sgtk.platform.current_bundle()
        self.sg = self.app.shotgun
        self.project = self.app.context.project

        self.setWindowTitle("Published Files")
        self.setGeometry(100, 100, 1200, 1000)
        #self.setMinimumSize(QSize(10000, 600))
        #self.setMaximumSize(QSize(10000, 1500))

        self.central_widget = QWidget(self)
        #self.setCentralWidget(self.central_widget)

        self.layout = QVBoxLayout(self.central_widget)

        self.table_view = QTableView(self)
        self.layout.addWidget(self.table_view)

        from .constants import EXTENSION_TYPE_MAP
        self._extension_types = EXTENSION_TYPE_MAP

        self.setup_table()

        # Populate the table with data
        self.populate_table()

    def populate_treeview_widget_perforce(self):
        pass

    def get_treeview_widget(self):
        return self.table_view

    def setup_table(self):
        # Define the headers for the table
        headers = ["Name", "Action", "Revision", "Size(MB)", " Extension", "Type", "Step",
                   "Destination Path", "Description", "Entity Sub-Folder"]

        # Create a table model and set headers
        self.model = QStandardItemModel(0, len(headers))
        self.model.setHorizontalHeaderLabels(headers)

        # Create a proxy model for sorting and grouping
        self.proxy_model = QtGui.QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)

        self.table_view.setModel(self.proxy_model)

        # Set the header to be clickable for sorting
        self.table_view.horizontalHeader().setSectionsClickable(True)
        self.table_view.horizontalHeader().setSortIndicatorShown(True)

        # Sort by the first column initially
        self.table_view.sortByColumn(0, Qt.AscendingOrder)

        # Grouping by "Entity Sub-Folder"
        self.table_view.setSortingEnabled(True)
        self.table_view.sortByColumn(7, Qt.AscendingOrder)
        #self.table_view.setGroupByColumn(7)

        # Fetch PublishedFiles data from Shotgun
        #data = self.fetch_published_files_data()

    def fetch_published_files_data(self):
        # Fetch PublishedFiles data from Shotgun
        project_id = self.project["id"]
        filters = [["entity", "is", {"type": "Project", "id": project_id}],
                   #Todo: Replace with the name of PublishedFileType
                   ["published_file_type", "is", {"type": "PublishedFileType", "name": "Some Published File Type"}]]
        fields = ["code", "path", "revision", "task", "created_by", "path", "path_cache", "image", "project", "published_file_type"]
        data = self.sg.find("PublishedFile", filters, fields)

        return data

    def print_sg_item(self, sg_item):
        for key, value in sg_item.items():
            msg = "{}: {}".format(key, value)
            logger.debug(msg)


    def populate_table(self):
        """ Populate the table with data"""
        row = 0
        for sg_item in self.sg_data:
            if not sg_item:
                continue
            self.print_sg_item(sg_item)
            # Extract relevant data from the Shotgun response
            name = sg_item.get("name", "N/A")
            action = sg_item.get("action") or sg_item.get("headAction") or "N/A"
            revision = sg_item.get("revision", "N/A")
            if revision != "N/A":
                revision = "#{}".format(revision)

            # Todo: get the size
            size = sg_item.get("fileSize", "N/A")
            if size != "N/A":
                size = "{:.2f}".format(int(size) / 1024 / 1024)
            path = sg_item.get("path", {}).get("local_path", "N/A") if "path" in sg_item else "N/A"
            file_extension = path.split(".")[-1] if path != "N/A" else "N/A"
            type = self._extension_types.get(file_extension, "N/A")
            # published_file_type = sg_item.get("published_file_type", {}).get("name", "N/A")
            # Todo: get the step
            step = sg_item.get("step", {}).get("name", "N/A")
            step = sg_item.get("task.Task.step.Step.code", "N/A") if step == "N/A" else step
            description = sg_item.get("description", "N/A")

            # task = sg_item.get("task", {}).get("name", "N/A")
            # task_status = sg_item.get("task.Task.sg_status_list", "N/A")
            # user = sg_item.get("created_by", {}).get("name", "N/A")

            entity_sub_folder = sg_item.get("entity.Sub-Folder", "N/A")

            # Insert data into the table
            self.insert_row(row, [name, action, revision, size, file_extension, type, step, path, description, entity_sub_folder])
            row += 1


    def insert_row(self, row, data):
        for col, value in enumerate(data):
            item = QStandardItem(str(value))
            self.model.setItem(row, col, item)

#Todo: do we need this?
def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("icon.png"))
    window = PublishedFileSPerforce()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
