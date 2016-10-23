from tornado.web import authenticated
from knimin.handlers.base import BaseHandler
from knimin import db
from knimin.handlers.access_decorators import set_access
from json import dumps


@set_access(['Admin'])
class PMPlateMapHandler(BaseHandler):
    @authenticated
    def get(self):
        target = self.get_argument('target', default='sample')
        pid = int(self.get_argument('id', default='0'))
        self.render('pm_plate_map.html', currentuser=self.current_user,
                    target=target, id=pid)


@set_access(['Admin'])
class PMPlateMapGetEmailsHandler(BaseHandler):
    @authenticated
    def get(self):
        self.write(dumps(db.get_emails()))


@set_access(['Admin'])
class PMPlateMapGetPlateTypesHandler(BaseHandler):
    @authenticated
    def get(self):
        self.write(dumps(db.get_plate_types()))


@set_access(['Admin'])
class PMPlateMapGetPlateIDsHandler(BaseHandler):
    @authenticated
    def get(self):
        self.write(dumps(db.get_sample_plate_ids()))


@set_access(['Admin'])
class PMPlateMapGetPlateInfoHandler(BaseHandler):
    @authenticated
    def get(self):
        pid = int(self.get_argument('id'))
        pinfo = db.read_sample_plate(pid)
        self.write(dumps(pinfo))


@set_access(['Admin'])
class PMPlateMapGetPlateLayoutHandler(BaseHandler):
    @authenticated
    def get(self):
        pid = int(self.get_argument('id'))
        playout = db.read_sample_plate_layout(pid)
        self.write(dumps(playout))
