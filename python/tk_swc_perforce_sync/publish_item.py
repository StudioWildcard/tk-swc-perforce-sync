import os
import sgtk
from tank.util import sgre as re
from urllib import request

import tempfile


from .date_time import create_human_readable_timestamp, create_human_readable_date, get_time_now
import datetime

from sgtk.util import login

logger = sgtk.platform.get_logger(__name__)


class PublishItem():
    """
   Publish Item
    """

    def __init__(self, sg_item):
        self.sg_item = sg_item
        self.app = sgtk.platform.current_bundle()
        self.entity = None
        self.publish_path = None
        self.settings = {
            "wire": "Alias File",
            "abc": "Alembic Cache",
            "max": "3dsmax Scene",
            "hrox": "NukeStudio Project",
            "hip": "Houdini Scene",
            "hipnc": "Houdini Scene",
            "hiplc": "Houdini Scene",
            "ma": "Maya Scene",
            "mb": "Maya Scene",
            "fbx": "Motion Builder FBX",
            "nk": "Nuke Script",
            "psd": "Photoshop Image",
            "psb": "Photoshop Image",
            "vpb": "VRED Scene",
            "vpe": "VRED Scene",
            "osb": "VRED Scene",
            "dpx": "Rendered Image",
            "exr": "Rendered Image",
            "tiff": "Texture",
            "tx": "Texture",
            "tga": "Texture",
            "dds": "Texture",
            "jpeg": "Image",
            "jpg":  "Image",
            "mov": "Movie",
            "mp4": "Movie",
            "pdf": "PDF",
        }
        self.status_dict = {
            "add": "p4add",
            "move/add": "p4add",
            "delete": "p4del",
            "edit": "p4edit"
        }

    def gui_publishing(self):

        engine = sgtk.platform.current_engine()
        engine.commands['Publish...']["callback"]()
        #engine.commands['SWCPublish...']["callback"]()


    def gui_publishing_2(self):
        tk_multi_publish2 = self.import_module("tk_multi_publish2")

        # the manager class provides the interface for publishing. We store a
        # reference to it to enable the create_publish_manager method exposed on
        # the application itself
        self._manager_class = tk_multi_publish2.PublishManager

        # make the util methods available via the app instance
        self._util = tk_multi_publish2.util

        # make the base plugins available via the app
        self._base_hooks = tk_multi_publish2.base_hooks

        display_name = self.get_setting("display_name")
        # "Publish Render" ---> publish_render
        command_name = display_name.lower()
        # replace all non alphanumeric characters by '_'
        command_name = re.sub(r"[^0-9a-zA-Z]+", "_", command_name)

        self.modal = self.get_setting("modal")

        pre_publish_hook_path = self.get_setting(self.CONFIG_PRE_PUBLISH_HOOK_PATH)
        self.pre_publish_hook = self.create_hook_instance(pre_publish_hook_path)

        # register command
        cb = lambda: tk_multi_publish2.show_dialog(self)
        menu_caption = "%s..." % display_name
        menu_options = {
            "short_name": command_name,
            "description": "Publishing of data to ShotGrid",
            # dark themed icon for engines that recognize this format
            "icons": {
                "dark": {"png": os.path.join(self.disk_location, "icon_256_dark.png")}
            },
        }
        self.engine.register_command(menu_caption, cb, menu_options)

    def gui_publishing_1(self):
        # need to have an engine running in a context where the publisher has been
        # configured.
        engine = sgtk.platform.current_engine()

        # get the publish app instance from the engine's list of configured apps
        publish_app = engine.apps.get("tk-multi-publish2")


        # ensure we have the publisher instance.
        if not publish_app:
            raise Exception("The publisher is not configured for this context.")


        # create a new publish manager instance
        manager = publish_app.create_publish_manager()

        # now we can run the collector that is configured for this context
        manager.collect_session()

        # collect some external files to publish
        # manager.collect_files([path1, path2, path3])

        # validate the items to publish
        tasks_failed_validation = manager.validate()

        # oops, some tasks are invalid. see if they can be fixed
        if tasks_failed_validation:
            fix_invalid_tasks(tasks_failed_validation)
            # try again here or bail

        logger.debug(">>>> Showing publisher ...")
        cb = lambda: publish_app.show_dialog(self)
        #publish_app.show_dialog(self)
        """
        # all good. let's publish and finalize
        try:
            manager.publish()
            # If a plugin needed to version up a file name after publish
            # it would be done in the finalize.
            manager.finalize()
        except Exception as error:
            logger.error("There was trouble trying to publish!")
            logger.error("Error: %s", error)
        """

    def commandline_publishing(self):
        """
        Publish the file
        """

        self.publish_path = self.get_publish_path()
        if not self.publish_path:
            logger.info("Unable to find publish file")
            return

        self.publish_version = self.get_publish_version()
        name = self.get_name(self.publish_path)
        published_file_name = self.get_published_file_name(self.publish_path)
        logger.debug("published_file_name is {}".format(published_file_name))
        #published_file_name = "{}2".format(published_file_name)
        #logger.debug("Modified published_file_name is {}".format(published_file_name))
        #sg_publish_file_name = self.get_SG_publish_file_name(self.publish_path)
        #logger.debug("SG published_file_name is {}".format(sg_publish_file_name))

        entity = self.get_publish_entity()
        entity_type = entity.get("type", None)
        entity_id = entity.get("id", 0)

        # tk = sgtk.sgtk_from_path(self.publish_path)
        tk = sgtk.sgtk_from_entity(entity_type, entity_id)

        # ctx = tk.context_from_path(self.publish_path)
        ctx = tk.context_from_entity(entity_type, entity_id)

        # logger.debug(">>>>>>>>>>>> entity is: {}".format(entity))

        # logger.debug(">>>>>>>>>>>> tk is: {}".format(tk))
        # logger.debug(">>>>>>>>>>>> context is: {}".format(ctx))
        """
        if self.sg_item:
            logger.debug(">>>>>>>>>>>> sg_item to be published, begin: ")
            for k, v in self.sg_item.items():
                logger.debug("{}: {}".format(k, v))
            logger.debug(">>>>>>>>>>>> End of sg_item to be published")
        """

        publish_time = self.get_publish_time()
        publish_type = self.get_publish_type(self.publish_path)

        publish_fields = self.get_publish_fields()
        sg_status_list = None
        #if publish_fields and "sg_status_list" in publish_fields:
        #    sg_status_list = publish_fields.get("sg_status_list", None)
        #    if sg_status_list and sg_status_list == "p4del":
        #        publish_fields["sg_status_list"] = "p4edit"

        description = self.get_description()
        thumbnail_url = self.get_thumbnail()



        #publish_dependencies_paths = self.get_publish_dependencies(settings, item)
        publish_user = self.get_publish_user()


        logger.info("Registering publish...")
        publish_data = {
            "tk": tk,
            "context": ctx,
            "entity": entity,
            "comment": description,
            "path": self.publish_path,
            "name": name,
            #"code": published_file_name,
            "version_number": self.publish_version,
            "published_file_type": publish_type,
            "sg_fields": publish_fields,
            "created_by": publish_user,
            "created_at": publish_time,
            "thumbnail_path": thumbnail_url,
            #"image": thumbnail_url,
            #"dependency_paths": publish_dependencies_paths,
            #"dependency_ids": publish_dependencies_ids,

        }


        # logger.debug("publish data: {}".format(publish_data))

        # create the publish and stash it in the item properties for other
        # plugins to use.

        sg_publish_result = sgtk.util.register_publish(**publish_data)

        logger.info("Publish registered!")
        # logger.debug(">>>>> Publish result: {}".format(sg_publish_result))

        if sg_publish_result:
            logger.debug(">>>>>>>>>>>> Publish result begin: ")
            for k, v in sg_publish_result.items():
                logger.debug("{}: {}".format(k, v))
            logger.debug(">>>>>>>>>>>> End of Publish result")
            #image_path = thumbnail_url
            #request.urlretrieve(thumbnail_url, image_path)
            #sg.download_attachment(thumbnail_url, image_path)
            temp_thumbnail_path = None
            if thumbnail_url:
                # Download the thumbnail image and save it to a local temporary file
                temp_thumbnail_path = os.path.join(tempfile.gettempdir(), "temp_thumbnail.png")
                # logger.debug(">>>>>>> temp_thumbnail_path: {}".format(temp_thumbnail_path))
                try:
                    import requests
                    response = requests.get(thumbnail_url)
                    if response.status_code == 200:
                        with open(temp_thumbnail_path, 'wb') as f:
                            f.write(response.content)
                    else:
                        logger.warning("Failed to download thumbnail image. Status code: %s", response.status_code)
                except Exception as e:
                    logger.error("Error downloading thumbnail image: %s", str(e))
            #if sg_status_list and sg_status_list == "p4del":
            #    publish_fields["sg_status_list"] = "p4del"
            updated_data = {
                'code': published_file_name,
                # "sg_fields": publish_fields
                #'image': temp_thumbnail_path,
            }
            try:
                if temp_thumbnail_path and os.path.exists(temp_thumbnail_path):
                    updated_data['image'] = temp_thumbnail_path
            except Exception as e:
                logger.debug("Error setting thumbnail image: %s", str(e))

            id = sg_publish_result.get("id", None)
            if id and updated_data:
                update_res = self.app.shotgun.update("PublishedFile", id, updated_data)
                # logger.debug("Updated published file: %s", update_res)

            # logger.debug("updated_data: {}".format(updated_data))
            id = sg_publish_result.get("id", None)
            if id and updated_data:
                update_res = self.app.shotgun.update("PublishedFile", id, updated_data)
                logger.debug("Updated published file: {}".format(update_res))

        return sg_publish_result



    def get_thumbnail(self):
        thumbnail = self.sg_item.get("image", None)
        # logger.debug("Publish image is: {}".format(thumbnail))
        return thumbnail

    def get_publish_entity(self):
        publish_entity = {}
        entity = self.sg_item.get("entity", None)
        if entity:
            publish_entity["id"] = entity.get("id", None)
            publish_entity["name"] = entity.get("code", None)
            publish_entity["type"] = entity.get("type", None)
        return publish_entity

    def get_publish_path(self):
        """
        Get publish path
        """
        # file_to_publish
        file_to_publish = None
        if 'path' in self.sg_item:
            file_to_publish = self.sg_item['path'].get('local_path', None)
        return file_to_publish

    def get_published_file_name(self, file_to_publish):
        """
        Get publish name
        """
        name = os.path.basename(file_to_publish)
        published_file_name = "{}#{}".format(name, self.publish_version)

        """
        published_file_name = self.sg_item.get("code", None)
        if published_file_name:
            return published_file_name

        published_file_name = os.path.basename(file_to_publish)
        version_number = self.sg_item.get("version_number", None)
        if version_number:
            published_file_name = "{}#{}".format(published_file_name, version_number)
            return published_file_name

        head_rev = self.sg_item.get("headRev", None)
        if head_rev:
            published_file_name = "{}#{}".format(published_file_name, head_rev)
            return published_file_name
        """

        return published_file_name

    def get_SG_publish_file_name(self, file_to_publish):
        publisher = sgtk.platform.current_bundle()
        return publisher.execute_hook_method(
            #"path_info", "get_publish_name", path=file_to_publish, sequence=sequence
            "path_info", "get_publish_name", path=file_to_publish
        )

    def get_name(self, file_to_publish):
        """
        Get publish name
        """
        name = os.path.basename(file_to_publish)
        return name

    def get_publish_type(self, publish_path):
        """
        Get a publish type
        """
        publish_type = None
        publish_path = os.path.splitext(publish_path)
        if len(publish_path) >= 2:
            extension = publish_path[1]

            # ensure lowercase and no dot
            if extension:
                extension = extension.lstrip(".").lower()
                publish_type = self.settings.get(extension, None)
                if not publish_type:
                    # publish type is based on extension
                    publish_type = "%s File" % extension.capitalize()
            else:
                # no extension, assume it is a folder
                publish_type = "Folder"
        return publish_type

    def get_publish_user(self):
        publish_user = None
        p4_user = self.sg_item.get("p4_user", None)
        if p4_user:
            publish_user = self.app.shotgun.find_one('HumanUser',
                                              [['sg_p4_user', 'is', p4_user]],
                                              ["id", "type", "email", "login", "name", "image"])
        logger.debug(">>> Publish user is: {}".format(publish_user))
        if not publish_user:
            action_owner = self.sg_item.get("actionOwner", None)
            if action_owner:
                publish_user = self.app.shotgun.find_one('HumanUser',
                                                     [['sg_p4_user', 'is', action_owner]],
                                                     ["id", "type", "email", "login", "name", "image"])
        logger.debug(">>>> Publish user is: {}".format(publish_user))
        if not publish_user:
            publish_user = login.get_current_user(self.app.sgtk)
            #publish_user = engine.get_current_user()
            #user = engine.get_current_login()
            #publish_user = connection.find_one(
            #    "HumanUser", [["id", "is", user["id"]]],
            #    ["id", "type", "email", "login", "name", "image"])
            # publish_user = publish_user.get("name", None)
        logger.debug(">>>>> Publish user is: {}".format(publish_user))
        return publish_user

    def get_publish_time(self):
        publish_time = None
        version_numer = int(self.sg_item.get("version_number", 0))
        if version_numer == 0:
            # No prior publish, use Perforce creation time as publish time
            dt = self.sg_item.get("headTime", None)
            logger.debug(">>>>> dt is: {}".format(dt))
            if dt:
                publish_time = create_human_readable_timestamp(dt)
        else:
            publish_time = get_time_now()
        logger.debug(">>>>> Publish time is: {}".format(publish_time))
        return publish_time


    def get_publish_version(self):
        # use the p4 revision number as the version number
        version_numer = int(self.sg_item.get("headRev", 0))

        action = self.sg_item.get("action", None)
        #if action and action in ["add", "move/add", "edit", "delete"]:
        if action and action in ["delete"]:
            # Get next version
            version_numer += 1
        return version_numer

    def get_publish_fields(self):
        sg_fields = {}
        try:
            sg_fields["sg_p4_depo_path"] = self.sg_item.get("depotFile", None)
            submittedChange = self.sg_item.get("submittedChange", None)
            if submittedChange:
                change_number = int(submittedChange)
            else:
                change_number = self.sg_item.get("headChange", None)
            if change_number:
                sg_fields["sg_p4_change_number"] = int(change_number)
            # sg_fields["Status"] = self.sg_item.get("headAction", None)
            # sg_fields["sg_status_list"] = self.sg_item.get("sg_status_list", None)

            sg_status_list = self.get_sg_status_list()
            sg_fields["sg_status_list"] =sg_status_list

            sg_fields["sg_p4_depo_path"] = self.sg_item.get("depotFile", None)
            sg_fields["task"] = self.sg_item.get("task", None)
            #sg_fields["task.Task.sg_status_list"] = self.sg_item.get("task.Task.sg_status_list", None)
            #sg_fields["task.Task.due_date"] = self.sg_item.get("task.Task.due_date", None)
            #sg_fields["task.Task.content"] = self.sg_item.get("task.Task.content", None)

            #published_file_name = self.get_published_file_name(self.publish_path)
            #sg_fields["code"] = published_file_name

            #sg_fields["task_uniqueness"] = self.sg_item.get("task_uniqueness", None)

            # sg_fields["link"] = self.entity.get("name", None)
            #logger.debug(">>>>> Publish sg_fields: {}".format(sg_fields))
        except:
            pass

        return sg_fields

    def get_sg_status_list(self):
        sg_status = None
        if "action" in self.sg_item:
            action = self.sg_item.get("action", None)
            if action:
                action = action.lower()
                sg_status = self.status_dict.get(action, None)
                return sg_status
        elif "headAction" in self.sg_item:
            action = self.sg_item.get("headAction", None)
            if action:
                action = action.lower()
                sg_status = self.status_dict.get(action, None)
                return sg_status
        elif "sg_status_list" in self.sg_item:
            return self.sg_item.get("sg_status_list", None)
        return sg_status



    def get_description(self):
        return self.sg_item.get("description", None)

    def get_next_version_number(self, item, path):

        # See how many prior versions there are
        filters = [
            ['entity', 'is', self._get_version_entity(item)]
        ]
        prior_versions = self.publisher.shotgun.find("Version",filters,['code'])

        #regex = r"(" + re.escape(publish_name.split('.')[0]) + r"){1}(\.v\d)?\.\w*$"
        regex = r"(" + re.escape(publish_name) + r"){1}(\.v\d)?\.\w*$"

        x = [i for i in prior_versions if re.match(regex,i['code'])]

        # Set the publish name of this item as the next version
        version_number = len(x)+1

        return version_number

    def _get_version_entity(self, item):
        """
        Returns the best entity to link the version to.
        """

        if item.context.entity:
            return item.context.entity
        elif item.context.project:
            return item.context.project
        else:
            return None



