#!/usr/bin/env python
from knimin.handlers.base import BaseHandler

from amgut.util import AG_DATA_ACCESS


class AGEditKitHandler(BaseHandler):
    def get(self):
        kitid = self.get_argument('kitid', None)
        if kitid is not None:
            kitdetails = AG_DATA_ACCESS.getAGKitDetails(kitid)
            email = AG_DATA_ACCESS.get_user_info(kitid)['email']
            self.render("ag_edit_kit.html", response=None, email=email,
                        kitinfo=kitdetails, loginerror='')

    def post(self):
        ag_kit_id = self.get_argument('ag_kit_id')
        kit_id = self.get_argument('kitid')
        passwd = self.get_argument('kit_password')
        swabs_per_kit = self.get_argument('swabs_per_kit')
        vercode = self.get_argument('kit_verification_code')
        try:
            AG_DATA_ACCESS.updateAGKit(ag_kit_id, kit_id, passwd,
                                       swabs_per_kit, vercode)
            self.render("ag_edit_kit.html", response='Good', email=None,
                        kitinfo=None, loginerror='')
        except:
            self.redner("ag_edit_kit.html", response='Bad', email=None,
                        kitinfo=None, loginerror='')
