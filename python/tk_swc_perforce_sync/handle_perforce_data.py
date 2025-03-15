from .publish_item import PublishItem
import sgtk
from collections import defaultdict
import os

logger = sgtk.platform.get_logger(__name__)

class PerforceData():
    def __init__(self, sg_data):
        self._sg_data = sg_data
        self._p4 = None
        self._connect()
        self._peforce_data = {}
        self.status_dict = {
            "add": "p4add",
            "delete": "p4del",
            "edit": "p4edit"
        }
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
            "jpg": "Image",
            "mov": "Movie",
            "mp4": "Movie",
            "pdf": "PDF"
        }

    def _get_peforce_data(self):
        sg_data_to_publish = None
        fstat_dict = {}
        # logger.debug(">>>>>>>>>>  self._sg_data is {}".format(self._sg_data))
        if self._sg_data:
            #if len(self._sg_data) <= 1:
            #    logger.debug(">>>>>>>>>>  Processing small data")
            #    self._sg_data = self._get_small_peforce_data(self._sg_data)
            #else:
            logger.debug(">>>>>>>>>>  Processing large data ..")
            sg_data_to_publish, fstat_dict = self._get_large_peforce_data()
            #logger.debug(">>>>>  sg_data_to_publish is: {}".format(sg_data_to_publish))
            #logger.debug("<<<<<<<<<  fstat_dict is: {}".format(fstat_dict))
        return sg_data_to_publish, fstat_dict

    def _get_large_peforce_data(self):
        """"
        Get large perforce data
        """
        logger.debug(">>>>>>>>>>  Get perforce data")
        item_path_dict = defaultdict(int)
        fstat_dict = {}
        if self._sg_data:
            for i, sg_item in enumerate(self._sg_data):
                if "path" in sg_item:
                    local_path = sg_item["path"].get("local_path", None)
                    if local_path:
                        # logger.debug("local_path is: {}".format(local_path))
                        # item_path = self._get_item_path(local_path)
                        item_path = os.path.dirname(local_path)
                        item_path_dict[item_path] += 1
            # logger.debug(">>>>>>>>>>  item path dict is: {}".format(item_path_dict))

            for key in item_path_dict:
                if key:
                    # logger.debug(">>>>>>>>>>  key is: {}".format(key))
                    key = "{}\\...".format(key)
                    # logger.debug("key is: {}".format(key))
                    fstat_list = self._p4.run("fstat", key)
                    for i, fstat in enumerate(fstat_list):
                        # if i == 0:
                        #    logger.debug(">>>>>>>>>  fstat is: {}".format(fstat))
                        # logger.debug("{}: >>>>>  fstat is: {}".format(i, fstat))
                        client_file = fstat.get('clientFile', None)
                        # if i == 0:
                        #    logger.debug(">>>>>>>>>>  client_file is: {}".format(client_file))
                        if client_file:
                            have_rev = fstat.get('haveRev', "0")
                            head_rev = fstat.get('headRev', "0")
                            modified_client_file = self._create_key(client_file)
                            if modified_client_file not in fstat_dict:
                                # if i == 0:
                                #    logger.debug(">>>>>>>>>>  client_file is: {}".format(client_file))
                                fstat_dict[modified_client_file] = {}
                                # fstat_dict[modified_client_file] = fstat
                                fstat_dict[modified_client_file]['clientFile'] = client_file
                                fstat_dict[modified_client_file]['haveRev'] = have_rev
                                fstat_dict[modified_client_file]['headRev'] = head_rev
                                fstat_dict[modified_client_file]['Published'] = False
                                fstat_dict[modified_client_file]['headModTime'] = fstat.get('headModTime', 'N/A')
                                fstat_dict[modified_client_file]['depotFile'] = fstat.get('depotFile', None)
                                fstat_dict[modified_client_file]['headAction'] = fstat.get('headAction', None)
                                fstat_dict[modified_client_file]['headChange'] = fstat.get('headChange', None)

            #logger.debug(">>>>>>>>>>  fstat_dict is: {}".format(fstat_dict))
            #for k, v in fstat_dict.items():
            #   logger.debug(">>>>>>>>>>  {}: {}".format(k, v))

            for i, sg_item in enumerate(self._sg_data):
                if "path" in sg_item:
                    if "local_path" in sg_item["path"]:
                        local_path = sg_item["path"].get("local_path", None)
                        modified_local_path = self._create_key(local_path)

                        if modified_local_path and modified_local_path in fstat_dict:

                            have_rev = fstat_dict[modified_local_path].get('haveRev', "0")
                            head_rev = fstat_dict[modified_local_path].get('headRev', "0")
                            fstat_dict[modified_local_path]['Published'] = True

                            sg_item["haveRev"], sg_item["headRev"] = have_rev, head_rev
                            sg_item["revision"] = "{}/{}".format(have_rev, head_rev)


            sg_data_to_publish = []
            for key in fstat_dict:
                if not fstat_dict[key]["Published"]:
                    sg_item = {}
                    # sg_item = fstat_dict[key]
                    file_path = fstat_dict[key].get("clientFile", None)
                    # logger.debug("----->>>>>>>    file_path: {}".format(file_path))
                    if file_path:
                        sg_item["name"] = os.path.basename(file_path)
                        sg_item["path"] = {}
                        sg_item["path"]["local_path"] = file_path
                    sg_item["code"] = "{}#{}".format(sg_item["name"], fstat_dict[key].get("headRev", 0))
                    #sg_item["type"] = "depotFile"
                    #sg_item["published_file_type"] = None
                    # sg_item["published_file_type"] = {'id': 265, 'name': 'Motion Builder FBX', 'type': 'PublishedFileType'}
                    have_rev = fstat_dict[key]["haveRev"]
                    head_rev = fstat_dict[key]["headRev"]
                    sg_item["haveRev"] = have_rev
                    sg_item["headRev"] = head_rev
                    sg_item["revision"] = "#{}/{}".format(have_rev, head_rev)
                    sg_item["created_at"] = 0
                    sg_item["depotFile"] = fstat_dict[key]["depotFile"]
                    sg_item["headChange"] = fstat_dict[key]["headChange"]
                    sg_item["headModTime"] = fstat_dict[key].get('headModTime', 0)
                    # sg_item["version_number"] = fstat_dict[key]["headRev"]

                    p4_status = fstat_dict[key].get("headAction", None)
                    sg_item["sg_status_list"] = self._get_p4_status(p4_status)

                    sg_item["depot_file_type"] = self._get_publish_type(file_path)
                    #  file_path : {}".format(file_path))
                    if file_path:
                        description, user = self._get_file_log(file_path)
                        if description:
                            sg_item["description"] = description
                        #if user:
                        #    sg_item["created_by"] = {}
                        #    sg_item["created_by"]["name"] = user
                        sg_data_to_publish.append(sg_item)
                        # logger.debug("----->>>>>>>    Data to publish: {}".format(sg_data_to_publish))
                        """
                        publisher = PublishItem(sg_item)
                        publish_result = publisher.publish_file()
                        publish_result["haveRev"] = have_rev
                        publish_result["headRev"] = head_rev
                        publish_result["revision"] = "#{}/{}".format(have_rev, head_rev)
                        if publish_result:
                            self._sg_data.append(publish_result)
                        """
            return sg_data_to_publish, fstat_dict
                    # logger.debug(">>>>>>>>>>>>>>>>> New SG item: {}".format(sg_item))


    def _get_file_log(self, file_path):
        try:
            filelog_list = self._p4.run("filelog", file_path)
            # logger.debug(">>>>>> filelog_list: {}".format(filelog_list))
            if filelog_list:
                filelog = filelog_list[0]
                # 'desc': ['- Climb Idle ']
                desc = filelog.get("desc", None)
                if desc:
                    desc = desc[0]
                    if desc.startswith("-"):
                        desc = desc[1:]
                    if desc.startswith(" "):
                        desc = desc[1:]
                # 'user': ['michael']
                user = filelog.get("user", None)
                if user:
                    user = user[0]
                    user = user.capitalize()
                return desc, user
            else:
                return None, None
        except:
            return None, None

    def _get_publish_type(self, publish_path):
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

    def _get_p4_status(self, p4_status):

        p4_status = p4_status.lower()
        sg_status = self.status_dict.get(p4_status, None)
        # logger.debug("p4_status: {}".format(p4_status))
        # logger.debug("sg_status: {}".format(sg_status))
        return sg_status

    def _create_key(self, file_path):
        if file_path:
            file_path = file_path.replace("\\", "")
            file_path = file_path.replace("/", "")
            file_path = file_path.lower()
        return file_path

    def _get_item_path(self, local_path):
        """
        Get item path
        """
        item_path = ""
        if local_path:
            local_path = local_path.split("\\")
            local_path = local_path[:7]
            item_path = "\\".join(local_path)
        return item_path

    def _get_small_peforce_data(self):
        """"
        Get small perforce data
        """

        if self._sg_data:
            for i, sg_item in enumerate(self._sg_data):
                if "path" in sg_item:
                    local_path = sg_item["path"].get("local_path", None)

                    # logger.debug(">>>>>>> local_path is: {}".format(local_path))
                    if local_path:
                        fstat_list = self._p4.run("fstat", local_path)
                        # logger.debug("fstat_list: {}".format(fstat_list))
                        fstat = fstat_list[0]
                        # logger.debug("fstat is: {}".format(fstat))
                        have_rev = fstat.get('haveRev', "0")
                        head_rev = fstat.get('headRev', "0")
                        sg_item["haveRev"], sg_item["headRev"] = have_rev, head_rev
                        sg_item["revision"] = "{}/{}".format(have_rev, head_rev)
                        # logger.debug("{}: Revision: {}".format(i, sg_item["revision"]))
                        # sg_item['depotFile'] = fstat.get('depotFile', None)

            # logger.debug("{}: SG item: {}".format(i, sg_item))

        return self._sg_data

    def _get_latest_revision(self, files_to_sync):
        for file_path in files_to_sync:
            p4_result = self._p4.run("sync", "-f", file_path + "#head")
            logger.debug("Syncing file: {}".format(file_path))

    def _to_sync(self, have_rev, head_rev):
        """
        Determine if we should sync the file
        """
        have_rev_int = int(have_rev)
        head_rev_int = int(head_rev)
        if head_rev_int > 0 and have_rev_int < head_rev_int:
            return True
        return False

    def _get_depot_path(self, local_path):
        """
        Convert local path to depot path
        For example, convert: 'B:\\Ark2Depot\\Content\\Base\\Characters\\Human\\Survivor\\Armor\\Cloth_T3\\_ven\\MDL\\Survivor_M_Armor_Cloth_T3_MDL.fbx'
        to "//Ark2Depot/Content/Base/Characters/Human/Survivor/Armor/Cloth_T3/_ven/MDL/Survivor_M_Armor_Cloth_T3_MDL.fbx"
        """
        local_path = local_path[2:]
        depot_path = local_path.replace("\\", "/")
        depot_path = "/{}".format(depot_path)
        return depot_path

    def _connect(self):
        """
        Connect to Perforce.  If a connection can't be established with
        the current settings then the connection UI will be shown.
        """
        try:
            if not self._p4:
                logger.debug("Connecting to perforce ...")
                self._fw = sgtk.platform.get_framework("tk-framework-perforce")
                self._p4 = self._fw.connection.connect()

        except:
            # Todo add error message
            logger.debug("Failed to connect!")
            raise

