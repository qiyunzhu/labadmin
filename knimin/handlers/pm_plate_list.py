#!/usr/bin/env python
from tornado.web import authenticated
from knimin.handlers.base import BaseHandler
from knimin import db
from knimin.handlers.access_decorators import set_access

"""
This page displays a list of plates (sample, DNA, library, )
Columns (general):
    ID, Name, Type, # samples, Person, Date
Columns for sample plate
    <DNA plate> / [create], [view/edit]
    edit properties
    edit layouts
Columns for DNA plate
Columns for library plate
view/edit (direct click)
set atts (multiple) (for DNA plates only)
"""


@set_access(['Admin'])
class PMPlateListHandler(BaseHandler):
    @authenticated
    def get(self):
        category = self.get_argument("category", default="sample")
        plates = db.get_sample_plate_list()
        self.render("pm_plate_list.html", currentuser=self.current_user,
                    category=category, plates=plates)

    @authenticated
    def post(self):
        action = self.get_argument("action")
        if action == 'migrate':
            db.migrate_data()
