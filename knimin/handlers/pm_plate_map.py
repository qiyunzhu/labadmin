#!/usr/bin/env python
from tornado.web import authenticated
from knimin.handlers.base import BaseHandler
from knimin import db
from knimin.handlers.access_decorators import set_access


@set_access(['Admin'])
class PMPlateMapHandler(BaseHandler):
    @authenticated
    def get(self):
        # warning: may have bugs in numbering
        # select the first sample plate by default
        target = self.get_argument("target", default="sample")
        id = int(self.get_argument("id", default="1"))
        # gets the total number of sample plates
        count = int(db.get_plate_count())
        # select the last sample plate
        if id == -1:
            id = plate_count
        ptype = db.get_sample_plate_type(id or None)
        layout = []
        info = {}
        if id:
            info = db.read_sample_plate(id)
            layout = db.read_sample_plate_layout(id)
        self.render("pm_plate_map.html", currentuser=self.current_user,
                    target=target, id=id, type=ptype, info=info, layout=layout)

    @authenticated
    def post(self):
        action = self.get_argument("action")
        if action == 'create':
            # do something
            self.render("pm_plate_map.html", currentuser=self.current_user,
                        plate_ids=plate_ids, plate_id=plate_id,
                        plate_details=plate_details)
        # elif action == 'modify':
            # do something
