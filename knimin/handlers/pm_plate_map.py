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
        action = self.get_argument('action', default=None)
        if not action:
            target = self.get_argument('target', default='sample')
            pid = int(self.get_argument('id', default='1'))
            ptype = db.get_sample_plate_type(pid or None)
            playout = []
            pinfo = {}
            if pid:
                pinfo = db.read_sample_plate(pid)
                playout = db.read_sample_plate_layout(pid)
            self.render('pm_plate_map.html', currentuser=self.current_user,
                        target=target, id=pid, type=ptype, info=pinfo,
                        layout=playout)
        elif action == 'emails':
            self.write(dumps(db.get_email_list()))
        elif action == 'plate_types':
            self.write(dumps(db.get_plate_type_list()))
        elif action == 'plate_ids':
            self.write(dumps(db.get_sample_plate_ids()))

    @authenticated
    def post(self):
        action = self.get_argument('action', default=None)
        print action
        # functions to be added
