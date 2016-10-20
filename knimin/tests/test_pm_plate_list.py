from unittest import main

from knimin.tests.tornado_test_base import TestHandlerBase
from knimin import db


class TestPMPlateListHandler(TestHandlerBase):
    def test_get_not_authed(self):
        response = self.get(
            '/pm_plate_list/')
        self.assertEqual(response.code, 200)
        self.assertTrue(
            response.effective_url.endswith('?next=%2Fpm_plate_list%2F'))

    def test_get(self):
        self.mock_login_admin()
        response = self.get('/pm_plate_list/')
        self.assertEqual(response.code, 200)
        # Test the page title
        self.assertIn('Sample Plate List', response.body)
        # Test the first sample plate
        p1 = db.get_sample_plate_list()[0]
        x = p1['fill'][1]
        battery = ''
        if x == 1.0:
            battery = 'full'
        elif x >= 0.667:
            battery = 'quarters'
        elif x > 0.333:
            battery = 'half'
        elif x > 0.0:
            battery = 'quarter'
        else:
            battery = 'empty'
        exp = ('<tr>\n'
               '<td>' + str(p1['id']) + '</td>\n'
               '<td><a href="/pm_plate_map/?target=sample&id=' +
               str(p1['id']) + '">' + p1['name'] + '</a></td>\n'
               '<td title="' + str(p1['type'][1]) + '">' + p1['type'][0] +
               '</td>\n'
               '<td>' + str(p1['fill'][0]) + '\n'
               '<span style="font-size:80%">\n'
               '\n'
               '\n'
               '<i class="fa fa-battery-three-' + battery + '"></i>\n'
               '\n'
               '</span></td>\n'
               '<td title="' + p1['study'][3] + '">' + str(p1['study'][1]) +
               '</td>\n'
               '<td>' + (p1['person'] or '-') + '</td>\n'
               '<td>' + (p1['date'] or '-') + '</td>\n'
               '<td style="padding:2px;">\n')
        self.assertIn(exp, response.body)

if __name__ == '__main__':
    main()
