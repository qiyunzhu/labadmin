#!/usr/bin/env python
from tornado.web import authenticated
from knimin.handlers.base import BaseHandler
from knimin import db
from knimin.handlers.access_decorators import set_access
from json import dumps


@set_access(['Admin'])
class PMPlateMapHandler(BaseHandler):
    @authenticated
    def get(self):
        action = self.get_argument("action", default=None)
        if not action:
            # warning: may have bugs in numbering
            # select the first sample plate by default
            target = self.get_argument('target', default='sample')
            pid = int(self.get_argument('id', default='1'))
            # gets the total number of sample plates
            count = int(db.get_plate_count())
            # select the last sample plate
            if pid == -1:
                pid = plate_count
            ptype = db.get_sample_plate_type(pid or None)
            layout = []
            info = {}
            if pid:
                info = db.read_sample_plate(pid)
                layout = db.read_sample_plate_layout(pid)
            self.render('pm_plate_map.html', currentuser=self.current_user,
                        target=target, id=pid, type=ptype, info=info,
                        layout=layout)
        elif action == 'emails':
            self.write(dumps(db.get_email_list()))
        elif action == 'plate_ids':
            self.write(dumps(db.get_sample_plate_ids()))

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
