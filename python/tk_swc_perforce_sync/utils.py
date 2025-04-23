# Copyright (c) 2015 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk
from sgtk.platform.qt import QtCore, QtGui
import os
logger = sgtk.platform.get_logger(__name__)


class ResizeEventFilter(QtCore.QObject):
    """
    Utility and helper.

    Event filter which emits a resized signal whenever
    the monitored widget resizes.

    You use it like this:

    # create the filter object. Typically, it's
    # it's easiest to parent it to the object that is
    # being monitored (in this case ui.thumbnail)
    filter = ResizeEventFilter(ui.thumbnail)

    # now set up a signal/slot connection so that the
    # __on_thumb_resized slot gets called every time
    # the widget is resized
    filter.resized.connect(__on_thumb_resized)

    # finally, install the event filter into the QT
    # event system
    ui.thumbnail.installEventFilter(filter)
    """

    resized = QtCore.Signal()

    def eventFilter(self, obj, event):
        """
        Event filter implementation.
        For information, see the QT docs:
        http://doc.qt.io/qt-4.8/qobject.html#eventFilter

        This will emit the resized signal (in this class)
        whenever the linked up object is being resized.

        :param obj: The object that is being watched for events
        :param event: Event object that the object has emitted
        :returns: Always returns False to indicate that no events
                  should ever be discarded by the filter.
        """
        # peek at the message
        if event.type() == QtCore.QEvent.Resize:
            # re-broadcast any resize events
            self.resized.emit()
        # pass it on!
        return False

class Icons(object):
    def __init__(self):
        self.repo_root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        self.p4_file_add_path = os.path.join(self.repo_root, "icons/p4_file_add.png")
        self.p4_file_add_icon = QtGui.QIcon(QtGui.QPixmap(self.p4_file_add_path))

        self.p4_file_edit_path = os.path.join(self.repo_root, "icons/p4_file_edit.png")
        self.p4_file_edit_icon = QtGui.QIcon(QtGui.QPixmap(self.p4_file_edit_path))

        self.p4_file_delete_path = os.path.join(self.repo_root, "icons/p4_file_delete.png")
        self.p4_file_delete_icon = QtGui.QIcon(QtGui.QPixmap(self.p4_file_delete_path))

        self.status_success_path = os.path.join(self.repo_root, "icons/status_success.png")
        self.status_success_icon = QtGui.QIcon(QtGui.QPixmap(self.status_success_path))

        self.status_validate_path = os.path.join(self.repo_root, "icons/status_validate.png")
        self.status_validate_icon = QtGui.QIcon(QtGui.QPixmap(self.status_validate_path))

    def get_icon_path(self, action):
        if action in ["add", "edit", "delete", "move/add"]:
            if action == "edit":
                return self.p4_file_edit_path
            elif action == "delete":
                return self.p4_file_delete_path
            else:
                return self.p4_file_add_path
        return None

    def get_icon_pixmap(self, action):
        if action in ["add", "edit", "delete", "move/add"]:
            if action == "edit":
                return self.p4_file_edit_icon
            elif action == "delete":
                return self.p4_file_delete_icon
            else:
                return self.p4_file_add_icon
        return None

    def get_sync_pixmap(self, sync_count):
        if sync_count >= 0:
            if sync_count == 0:
                return self.status_success_icon
            elif sync_count >= 0:
                return self.status_validate_icon
            # For any other case (Future update), return the validate icon
            else:
                return self.status_validate_icon
        return None

def create_overlayed_user_publish_thumbnail(publish_pixmap, user_pixmap):
    """
    Creates a sqaure 75x75 thumbnail with an optional overlayed pixmap.
    """
    # create a 100x100 base image
    base_image = QtGui.QPixmap(75, 75)
    base_image.fill(QtCore.Qt.transparent)

    painter = QtGui.QPainter(base_image)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)

    # scale down the thumb
    if not publish_pixmap.isNull():
        thumb_scaled = publish_pixmap.scaled(
            75, 75, QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation
        )

        # now composite the thumbnail on top of the base image
        # bottom align it to make it look nice
        thumb_img = thumb_scaled.toImage()
        brush = QtGui.QBrush(thumb_img)
        painter.save()
        painter.setBrush(brush)
        painter.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        painter.drawRect(0, 0, 75, 75)
        painter.restore()

    if user_pixmap and not user_pixmap.isNull():

        # overlay the user picture on top of the thumbnail
        user_scaled = user_pixmap.scaled(
            30, 30, QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation
        )
        user_img = user_scaled.toImage()
        user_brush = QtGui.QBrush(user_img)
        painter.save()
        painter.translate(42, 42)
        painter.setBrush(user_brush)
        painter.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        painter.drawRect(0, 0, 30, 30)
        painter.restore()

    painter.end()

    return base_image


def create_overlayed_folder_thumbnail(image):
    """
    Given a shotgun thumbnail, create a folder icon
    with the thumbnail composited on top. This will return a
    512x400 pixmap object.

    :param image: QImage containing a thumbnail
    :returns: QPixmap with a 512x400 px image
    """
    # folder icon size
    CANVAS_WIDTH = 512
    CANVAS_HEIGHT = 400

    # corner radius when we draw
    CORNER_RADIUS = 10

    # maximum sized canvas we can draw on *inside* the
    # folder icon graphic
    MAX_THUMB_WIDTH = 460
    MAX_THUMB_HEIGHT = 280

    # looks like there are some pyside related memory issues here relating to
    # referencing a resource and then operating on it. Just to be sure, make
    # make a full copy of the resource before starting to manipulate.
    base_image = QtGui.QPixmap(":/res/folder_512x400.png")

    # now attempt to load the image
    # pixmap will be a null pixmap if load fails
    thumb = QtGui.QPixmap.fromImage(image)

    if not thumb.isNull():

        thumb_scaled = thumb.scaled(
            MAX_THUMB_WIDTH,
            MAX_THUMB_HEIGHT,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )

        # now composite the thumbnail
        thumb_img = thumb_scaled.toImage()
        brush = QtGui.QBrush(thumb_img)

        painter = QtGui.QPainter(base_image)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setBrush(brush)

        # figure out the offset height wise in order to center the thumb
        height_difference = CANVAS_HEIGHT - thumb_scaled.height()
        width_difference = CANVAS_WIDTH - thumb_scaled.width()

        inlay_offset_w = (width_difference / 2) + (CORNER_RADIUS / 2)
        # add a 30 px offset here to push the image off center to
        # fit nicely inside the folder icon
        inlay_offset_h = (height_difference / 2) + (CORNER_RADIUS / 2) + 30

        # note how we have to compensate for the corner radius
        painter.translate(inlay_offset_w, inlay_offset_h)
        painter.drawRoundedRect(
            0,
            0,
            thumb_scaled.width() - CORNER_RADIUS,
            thumb_scaled.height() - CORNER_RADIUS,
            CORNER_RADIUS,
            CORNER_RADIUS,
        )

        painter.end()

    return base_image


def create_overlayed_publish_thumbnail(image):
    """
    Given a shotgun thumbnail, create a publish icon
    with the thumbnail composited onto a centered otherwise empty canvas.
    This will return a 512x400 pixmap object.


    :param image: QImage containing a thumbnail
    :returns: QPixmap with a 512x400 px image
    """

    CANVAS_WIDTH = 512
    CANVAS_HEIGHT = 400
    CORNER_RADIUS = 10

    # get the 512 base image
    base_image = QtGui.QPixmap(CANVAS_WIDTH, CANVAS_HEIGHT)
    base_image.fill(QtCore.Qt.transparent)

    # now attempt to load the image
    # pixmap will be a null pixmap if load fails
    thumb = QtGui.QPixmap.fromImage(image)

    if not thumb.isNull():

        # scale it down to fit inside a frame of maximum 512x512
        thumb_scaled = thumb.scaled(
            CANVAS_WIDTH,
            CANVAS_HEIGHT,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )

        # now composite the thumbnail on top of the base image
        # bottom align it to make it look nice
        thumb_img = thumb_scaled.toImage()
        brush = QtGui.QBrush(thumb_img)

        painter = QtGui.QPainter(base_image)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setBrush(brush)

        # figure out the offsets in order to center the thumb
        height_difference = CANVAS_HEIGHT - thumb_scaled.height()
        width_difference = CANVAS_WIDTH - thumb_scaled.width()

        # center it horizontally
        inlay_offset_w = (width_difference / 2) + (CORNER_RADIUS / 2)
        # center it vertically
        inlay_offset_h = (height_difference / 2) + (CORNER_RADIUS / 2)

        # note how we have to compensate for the corner radius
        painter.translate(inlay_offset_w, inlay_offset_h)
        painter.drawRoundedRect(
            0,
            0,
            thumb_scaled.width() - CORNER_RADIUS,
            thumb_scaled.height() - CORNER_RADIUS,
            CORNER_RADIUS,
            CORNER_RADIUS,
        )

        painter.end()

    return base_image


def filter_publishes(app, sg_data_list):
    """
    Filters a list of shotgun published files based on the filter_publishes
    hook.

    :param app:           app that has the hook.
    :param sg_data_list:  list of shotgun dictionaries, as returned by the
                          find() call.
    :returns:             list of filtered shotgun dictionaries, same form as
                          the input.
    """
    try:
        # Constructing a wrapper dictionary so that it's future proof to
        # support returning additional information from the hook
        hook_publish_list = [{"sg_publish": sg_data} for sg_data in sg_data_list]

        hook_publish_list = app.execute_hook(
            "filter_publishes_hook", publishes=hook_publish_list
        )
        if not isinstance(hook_publish_list, list):
            app.log_error(
                "hook_filter_publishes returned an unexpected result type \
                '%s' - ignoring!"
                % type(hook_publish_list).__name__
            )
            hook_publish_list = []

        # split back out publishes:
        sg_data_list = []
        for item in hook_publish_list:
            sg_data = item.get("sg_publish")
            if sg_data:
                sg_data_list.append(sg_data)

    except:
        app.log_exception("Failed to execute 'filter_publishes_hook'!")
        sg_data_list = []

    return sg_data_list


def resolve_filters(filters):
    """
    When passed a list of filters, it will resolve strings found in the filters using the context.
    For example: '{context.user}' could get resolved to {'type': 'HumanUser', 'id': 86, 'name': 'Philip Scadding'}

    :param filters: A list of filters that has usually be defined by the user or by default in the environment yml
    config or the app's info.yml. Supports complex filters as well. Filters should be passed in the following format:
    [[task_assignees, is, '{context.user}'],[sg_status_list, not_in, [fin,omt]]]

    :return: A List of filters for use with the shotgun api
    """
    app = sgtk.platform.current_bundle()

    resolved_filters = []
    for filter in filters:
        if type(filter) is dict:
            resolved_filter = {
                "filter_operator": filter["filter_operator"],
                "filters": resolve_filters(filter["filters"]),
            }
        else:
            resolved_filter = []
            for field in filter:
                if field == "{context.entity}":
                    field = app.context.entity
                elif field == "{context.step}":
                    field = app.context.step
                elif field == "{context.project}":
                    field = app.context.project
                elif field == "{context.project.id}":
                    if app.context.project:
                        field = app.context.project.get("id")
                    else:
                        field = None
                elif field == "{context.task}":
                    field = app.context.task
                elif field == "{context.user}":
                    field = app.context.user
                resolved_filter.append(field)
        resolved_filters.append(resolved_filter)
    return resolved_filters

def get_action_icon(action):
    """ Get the icon for the action
    """
    repo_root = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    p4_file_add_path = os.path.join(repo_root, "icons/p4_file_add.png")
    p4_file_add_icon = QtGui.QIcon(QtGui.QPixmap(p4_file_add_path))

    p4_file_edit_path = os.path.join(repo_root, "icons/p4_file_edit.png")
    p4_file_edit_icon = QtGui.QIcon(QtGui.QPixmap(p4_file_edit_path))

    p4_file_delete_path = os.path.join(repo_root, "icons/p4_file_delete.png")
    p4_file_delete_icon = QtGui.QIcon(QtGui.QPixmap(p4_file_delete_path))

    if action in ["add", "edit", "delete", "move/add"]:
        if action == "edit":
            return p4_file_edit_icon, p4_file_edit_path
        elif action == "delete":
            return p4_file_delete_icon, p4_file_delete_path
        else:
            return p4_file_add_icon, p4_file_add_path
    return None, None

def check_validity_by_path_parts(swc_fw, sg_item):
    """
    Check if the filepath leads to a valid ShotGrid entity
    :param sg_item: ShotGrid item information
    :return: (entity_dict, None) if context is found, else (None, None)
    """
    if not sg_item or "path" not in sg_item:
        return None, None

    # logger.debug(f">>>>> Checking validity by path parts: sg_item: {sg_item}")
    local_path = sg_item["path"].get("local_path")

    try:
        target_context = swc_fw.find_task_context(local_path)
    except AttributeError as e:
        logger.debug(f">>>>> Error in find_task_context: {e}")
        return None, None

    if target_context and target_context.entity:
        entity = {
            "type": target_context.entity.get("type"),
            "id": target_context.entity.get("id"),
            "name": target_context.entity.get("name")
        }
        return entity, None

    return None, None


def check_validity_by_path_parts_1(swc_fw, sg_item):
    """
    Check if the filepath leads to a valid ShotGrid entity
    :param sg_item: ShotGrid item information
    :return: entity and published file info if found, None otherwise
    """
    target_context = None
    if not sg_item or "path" not in sg_item:
        return None, None

    logger.debug(f">>>>> Checking validity by path parts: sg_item: {sg_item}")

    local_path = sg_item["path"].get("local_path", None)

    try:
        target_context = swc_fw.find_task_context(local_path)
    except(AttributeError):
        logger.debug(f">>>>> {AttributeError}")

    if target_context:
        entity = target_context
        return entity, None

    return None, None

def check_validity_by_published_file(sg_item):
    """
    Check if the filepath leads to a valid shotgrid entity
    :param sg_item: Shotgrid item information
    :return: entity and published file info if found, None otherwise
    """
    if not sg_item:
        return None, None

    #logger.debug(">>>>> Checking validity by published file: sg_item: {}".format(sg_item))

    if "path" in sg_item:
        local_path = sg_item["path"].get("local_path", None)
        logger.debug(">>>>> Checking validity by published file: local_path: {}".format(local_path))
        if local_path:

            if not os.path.exists(local_path):
                msg = "File does not exist locally: {}".format(local_path)
                logger.debug(">>>>> {}".format(msg))
                # self.send_error_message(msg)
                # return None, None

            sg = sgtk.platform.current_bundle()
            #logger.debug(">>>>> local_path: {}".format(local_path))
            current_relative_path = fix_query_path(local_path)
            #logger.debug(">>>>>>>>>>>>>> current_relative_path: {}".format(current_relative_path))
            file_name = os.path.basename(local_path)
            #logger.debug(">>>>> file_name: {}".format(file_name))
            local_path = local_path.replace("\\", "/")

            # Search by file name
            filter_query = [['path_cache', 'contains', current_relative_path]]
            fields = ["entity", "path_cache", "path", "version_number", "name",
                      "description", "created_at", "created_by", "image",
                      "published_file_type", "task", "task.Task.content", "task.Task.sg_status_list"]

            published_files = sg.shotgun.find("PublishedFile", filter_query, fields,
                                              order=[{'field_name': 'version_number', 'direction': 'desc'}])

            for published_file in published_files:
                #logger.debug(">>>>> published_file: ")
                #for k, v in published_file.items():
                #    logger.debug(">>>>> {} : {}".format(k, v))
                if "path" in published_file and "local_path" in published_file["path"]:
                    query_local_path = published_file["path"]["local_path"].replace("\\", "/")
                    if query_local_path.endswith(current_relative_path):
                        entity = published_file.get("entity", None)
                        if entity:
                            return entity, published_file

            msg = "Failed to retrieve the associated Shotgrid entity for the file located at {}".format(local_path)
            logger.debug(">>>>> {}".format(msg))

    return None, None


def fix_query_path(current_relative_path):
    # Normalize the current relative path to ensure consistent path separators
    normalized_path = os.path.normpath(current_relative_path)

    # Split the path into drive and the rest
    drive, path_without_drive = os.path.splitdrive(normalized_path)

    # Remove leading slashes (if any) from the path without the drive
    trimmed_path = path_without_drive.lstrip(os.sep)
    trimmed_path = trimmed_path.replace("\\", "/")

    return trimmed_path