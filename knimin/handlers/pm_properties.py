from tornado.web import authenticated
# from tornado.escape import json_encode
from knimin.handlers.base import BaseHandler
# from knimin import db
from knimin.handlers.access_decorators import set_access


@set_access(['Admin'])
class PMPropertiesHandler(BaseHandler):
    @authenticated
    def get(self):
        # do something
        self.render('pm_properties.html', currentuser=self.current_user)

    @authenticated
    def post(self):
        action = self.get_argument('action')
        if action == 'create':
            print 'Hi there!'
            # do something
