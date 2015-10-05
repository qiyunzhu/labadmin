from contextlib import contextmanager
from collections import defaultdict, namedtuple
from re import sub
from hashlib import md5
from datetime import datetime, time, timedelta
import json

from bcrypt import hashpw, gensalt

from psycopg2 import connect, Error as PostgresError
from psycopg2.extras import DictCursor

from util import make_valid_kit_ids, make_verification_code, make_passwd
from constants import md_lookup, month_lookup
from geocoder import geocode, Location, GoogleAPILimitExceeded


class IncorrectEmailError(Exception):
    pass


class IncorrectPasswordError(Exception):
    pass


class SQLHandler(object):
    """Encapsulates the DB connection with the Postgres DB

    Sourced from QIITA's SQLConnectionHandler
    """
    def __init__(self, config):
        self._connection = connect(user=config.db_user,
                                   password=config.db_password,
                                   database=config.db_database,
                                   host=config.db_host,
                                   port=config.db_port)

    def __del__(self):
        self._connection.close()

    @contextmanager
    def cursor(self):
        """ Returns a Postgres cursor

        Returns
        -------
        pgcursor : psycopg2.cursor
        """
        with self._connection.cursor(cursor_factory=DictCursor) as cur:
            yield cur

    def _check_sql_args(self, sql_args):
        """ Checks that sql_args have the correct type

        Inputs:
            sql_args: SQL arguments

        Raises a TypeError if sql_args does not have the correct type,
            otherwise it just returns the execution to the caller
        """
        # Check that sql arguments have the correct type
        if sql_args and type(sql_args) not in [tuple, list, dict]:
            raise TypeError("sql_args should be tuple, list or dict. Found %s "
                            % type(sql_args))

    @contextmanager
    def _sql_executor(self, sql, sql_args=None, many=False):
        """Executes an SQL query

        Parameters
        ----------
        sql: str
            The SQL query
        sql_args: tuple or list, optional
            The arguments for the SQL query
        many: bool, optional
            If true, performs an execute many call

        Returns
        -------
        pgcursor : psycopg2.cursor
            The cursor in which the SQL query was executed

        Raises
        ------
        ValueError
            If there is some error executing the SQL query
        """
        # Check that sql arguments have the correct type
        if many:
            for args in sql_args:
                self._check_sql_args(args)
        else:
            self._check_sql_args(sql_args)

        # Execute the query
        with self.cursor() as cur:
            try:
                if many:
                    cur.executemany(sql, sql_args)
                else:
                    cur.execute(sql, sql_args)
                yield cur
                self._connection.commit()
            except PostgresError as e:
                self._connection.rollback()
                try:
                    err_sql = cur.mogrify(sql, sql_args)
                except:
                    err_sql = cur.mogrify(sql, sql_args[0])
                raise ValueError(("\nError running SQL query: %s"
                                  "\nError: %s" % (err_sql, e)))

    def execute_fetchall(self, sql, sql_args=None):
        """ Executes a fetchall SQL query

        Parameters
        ----------
        sql: str
            The SQL query
        sql_args: tuple or list, optional
            The arguments for the SQL query

        Returns
        ------
        list of tuples
            The results of the fetchall query

        Note: from psycopg2 documentation, only variable values should be bound
            via sql_args, it shouldn't be used to set table or field names. For
            those elements, ordinary string formatting should be used before
            running execute.
        """
        with self._sql_executor(sql, sql_args) as pgcursor:
            result = pgcursor.fetchall()
        return result

    def execute_fetchone(self, sql, sql_args=None):
        """ Executes a fetchone SQL query

        Parameters
        ----------
        sql: str
            The SQL query
        sql_args: tuple or list, optional
            The arguments for the SQL query

        Returns
        -------
        Tuple
            The results of the fetchone query

        Notes
        -----
        from psycopg2 documentation, only variable values should be bound
            via sql_args, it shouldn't be used to set table or field names. For
            those elements, ordinary string formatting should be used before
            running execute.
        """
        with self._sql_executor(sql, sql_args) as pgcursor:
            result = pgcursor.fetchone()
        return result

    def execute_fetchdict(self, sql, sql_args=None):
        """ Executes a fetchall SQL query and returns each row as a dict

        Parameters
        ----------
        sql: str
            The SQL query
        sql_args: tuple or list, optional
            The arguments for the SQL query

        Returns
        -------
        list of dict
            The results of the query as [{colname: val, colname: val, ...}, ...]

        Notes
        -----
        from psycopg2 documentation, only variable values should be bound
            via sql_args, it shouldn't be used to set table or field names. For
            those elements, ordinary string formatting should be used before
            running execute.
        """
        with self._sql_executor(sql, sql_args) as pgcursor:
            result = [dict(row) for row in pgcursor.fetchall()]
        return result

    def execute(self, sql, sql_args=None):
        """ Executes an SQL query with no results

        Parameters
        ----------
        sql: str
            The SQL query
        sql_args: tuple or list, optional
            The arguments for the SQL query

        Notes
        -----
        from psycopg2 documentation, only variable values should be bound
            via sql_args, it shouldn't be used to set table or field names. For
            those elements, ordinary string formatting should be used before
            running execute.
        """
        with self._sql_executor(sql, sql_args):
            pass

    def executemany(self, sql, sql_args_list):
        """ Executes an executemany SQL query with no results

        Parameters
        ----------
        sql: str
            The SQL query
        sql_args: list of tuples
            The arguments for the SQL query

        Note: from psycopg2 documentation, only variable values should be bound
            via sql_args, it shouldn't be used to set table or field names. For
            those elements, ordinary string formatting should be used before
            running execute.
        """
        with self._sql_executor(sql, sql_args_list, True):
            pass

    def execute_proc_return_cursor(self, procname, proc_args):
        """Executes a stored procedure and returns a cursor

        Parameters
        ----------
        procname: str
            the name of the stored procedure
        proc_args: list
            arguments sent to the stored procedure
        """
        proc_args.append('cur2')
        cur = self._connection.cursor()
        cur.callproc(procname, proc_args)
        cur.close()
        return self._connection.cursor('cur2')


class KniminAccess(object):
    # arbitrary, unique ID and value
    human_sites = ['Stool',
                   'Mouth',
                   'Right hand',
                   'Left hand',
                   'Forehead',
                   'Nares',
                   'Hair',
                   'Tears',
                   'Nasal mucus',
                   'Ear wax',
                   'Vaginal mucus']

    animal_sites = ['Stool',
                    'Mouth',
                    'Nares',
                    'Ears',
                    'Skin',
                    'Fur']

    general_sites = ['Animal Habitat',
                     'Biofilm',
                     'Dust',
                     'Food',
                     'Fermented Food',
                     'Indoor Surface',
                     'Outdoor Surface',
                     'Plant habitat',
                     'Soil',
                     'Sole of shoe',
                     'Water']

    def __init__(self, config):
        self._con = SQLHandler(config)
        self._con.execute('set search_path to ag, barcodes, public')

    def _get_col_names_from_cursor(self, cur):
        if cur.description:
            return [x[0] for x in cur.description]
        else:
            return []

    def get_barcode_details(self, barcode):
        """
        Returns the general barcode details for a barcode
        """
        sql = """SELECT  create_date_time, status, scan_date,
                  sample_postmark_date,
                  biomass_remaining, sequencing_status, obsolete
                  FROM    barcode
                  WHERE barcode = %s"""
        res = self._con.execute_fetchdict(sql, [barcode])
        return res[0] if res else {}

    def get_ag_barcode_details(self, barcodes):
        """Retrieve sample, kit, and login details by barcode

        Parameters
        ----------
        barcodes : iterable of str
            The list of barcodes for which to get login details

        Returns
        -------
        dict of dict
            {barcode: {column: value}, ...}
        """
        sql = """SELECT barcode, *
                 FROM ag_kit_barcodes
                 JOIN ag_kit USING (ag_kit_id)
                 JOIN ag_login USING (ag_login_id)
                 WHERE barcode in %s"""
        results = {row[0]: dict(row)
                   for row in self._con.execute_fetchall(sql, [tuple(barcodes)])}
        return results

    def get_surveys(self, barcodes):
        """Retrieve surveys for specific barcodes

        Parameters
        ----------
        barcodes : iterable of str
            The list of barcodes for which metadata will be retrieved

        Returns
        -------
        dict
            {survey: {barcode: {shortname: response, ...}, ...}, ...}

        Notes
        -----
        For multiples, the shortname that is used in the returned dict is
        combined with a modified version of the response. Specifically, spaces
        and non-alphanumeric characters are replaced with underscroes, and the
        response is capitalized. E.g., If the person is allergic to "Tree
        nuts", the key in the dict would be "ALLERGIC_TO_TREE_NUTS" (the
        ALLERGIC_TO portion taken from the shortname column of the question
        table).
        """
        # SINGLE answers SQL
        single_sql = \
            """SELECT S.survey_id, barcode, question_shortname, response
               FROM ag.ag_kit_barcodes
               JOIN ag.survey_answers SA USING (survey_id)
               JOIN ag.survey_question USING (survey_question_id)
               JOIN ag.survey_question_response_type USING (survey_question_id)
               JOIN ag.group_questions GQ USING (survey_question_id)
               JOIN ag.surveys S USING (survey_group)
               WHERE survey_response_type='SINGLE' AND barcode in %s"""

        # MULTIPLE answers SQL
        multiple_sql = \
            """SELECT S.survey_id, barcode, question_shortname,
                      array_agg(response) as responses
               FROM ag.ag_kit_barcodes
               JOIN ag.survey_answers USING (survey_id)
               JOIN ag.survey_question USING (survey_question_id)
               JOIN ag.survey_question_response_type USING (survey_question_id)
               JOIN ag.group_questions USING (survey_question_id)
               JOIN ag.surveys S USING (survey_group)
               WHERE survey_response_type='MULTIPLE' AND barcode in %s
               GROUP BY S.survey_id, barcode, question_shortname"""

        # Also need to get the possible responses for multiples
        multiple_responses_sql = \
            """SELECT question_shortname, response
               FROM survey_question
               JOIN survey_question_response_type USING (survey_question_id)
               JOIN survey_question_response USING (survey_question_id)
               WHERE survey_response_type = 'MULTIPLE'"""

        # STRING and TEXT answers SQL
        others_sql = \
            """SELECT S.survey_id, barcode, question_shortname, response
               FROM ag.ag_kit_barcodes
               JOIN ag.survey_answers_other SA USING (survey_id)
               JOIN ag.survey_question USING (survey_question_id)
               JOIN ag.survey_question_response_type USING (survey_question_id)
               JOIN ag.group_questions GQ USING (survey_question_id)
               JOIN ag.surveys S USING (survey_group)
               WHERE survey_response_type in ('STRING', 'TEXT')
               AND barcode in %s"""

        # Formats a question and response for a MULTIPLE question into a header
        def _translate_multiple_response_to_header(question, response):
            response = response.replace(" ", "_")
            response = sub('\W', '', response)
            header = '_'.join([question, response])
            return header.upper()

        # For each MULTIPLE question, build a dict of the possible responses
        # and what the header should be for the column representing the
        # response
        multiples_headers = defaultdict(dict)
        for question, response in self._con.execute_fetchall(
                multiple_responses_sql):
            multiples_headers[question][response] = \
                _translate_multiple_response_to_header(question, response)

        # this function reduces code duplication by generalizing as much
        # as possible how questions and responses are fetched from the db
        bc = tuple(barcodes)

        def _format_responses_as_dict(sql, json=False, multiple=False):
            ret_dict = defaultdict(lambda: defaultdict(dict))
            for survey, barcode, q, a in self._con.execute_fetchall(sql, [bc]):
                if json:
                    # Taking this slice here since all json are single-element
                    # lists
                    a = a[2:-2]

                    # replace all non-alphanumerics with underscore
                    a = sub('[^0-9a-zA-Z.,;/_() -]', '_', a)
                if multiple:
                    for response, header in multiples_headers[q].items():
                        ret_dict[survey][barcode][header] = \
                            'Yes' if response in a else 'No'
                else:
                    ret_dict[survey][barcode][q] = a
            return ret_dict

        single_results = _format_responses_as_dict(single_sql)
        others_results = _format_responses_as_dict(others_sql, json=True)
        multiple_results = _format_responses_as_dict(multiple_sql,
                                                     multiple=True)

        # combine the results for each barcode
        for survey, barcodes in single_results.items():
            for barcode in barcodes:
                single_results[survey][barcode].update(
                    others_results[survey][barcode])
                single_results[survey][barcode].update(
                    multiple_results[survey][barcode])

        # At this point, the variable name is a misnomer, as it contains
        # the results from all question types
        return single_results

    def _months_between_dates(self, d1, d2):
        """Calculate the number of months between two dates

        Parameters
        ----------
        d1 : datetime
            First date
        d2 : datetime
            Second date

        Raises
        ------
        ValueError
            if the first date is greater than the second date

        Notes
        -----
        - Assumes the first date d1 is not greater than the second date d2
        - Ignores the day (uses only year and month)
        """
        if d1 > d2:
            raise ValueError("First date must not be greater than the second")

        # Calculate the number of 12-month periods between the years
        return (d2.year - d1.year) * 12 + (d2.month - d1.month)

    def format_survey_data(self, md):
        """Modifies barcode metadata to include all columns and correct units

        Specifically, this function:
        - corrects height and weight to be in the same units (cm and kg,
          respectively)
        - Adds AGE_MONTHS and AGE_YEARS columns
        - Adds standard columns for EBI and MiMARKS

        Parameters
        ----------
        md : dict of dict of dict
            E.g., the output from get_barcode_metadata.
            {survey: {barcode: {shortname: response, ...}, ...}, ...}

        Returns
        -------
        dict of dict of dict
        """
        # get barcode information
        all_barcodes = set().union(*[set(md[s]) for s in md])
        barcode_info = self.get_ag_barcode_details(all_barcodes)

        # Human survey (id 1)
        # tuples are latitude, longitude, elevation, state
        zipcode_sql = """SELECT zipcode, country, round(latitude::numeric, 1),
                             round(longitude::numeric,1),
                             round(elevation::numeric, 1), state
                         FROM zipcodes"""
        zip_lookup = defaultdict(dict)
        for row in self._con.execute_fetchall(zipcode_sql):
            zip_lookup[row[0]][row[1]] = map(
                lambda x: x if x is not None else 'Unspecified', row[2:])

        country_sql = "SELECT country, EBI from ag.iso_country_lookup"
        country_lookup = dict(self._con.execute_fetchall(country_sql))
        # Add for scrubbed testing database
        country_lookup['REMOVED'] = 'REMOVED'

        survey_sql = "SELECT barcode, survey_id FROM ag.ag_kit_barcodes"
        survey_lookup = dict(self._con.execute_fetchall(survey_sql))

        for barcode, responses in md[1].items():
            # convert numeric fields
            for field in ('HEIGHT_CM', 'WEIGHT_KG'):
                md[1][barcode][field] = sub('[^0-9.]',
                                            '', md[1][barcode][field])
                if md[1][barcode][field]:
                    md[1][barcode][field] = float(md[1][barcode][field])

            # Correct height units
            if responses['HEIGHT_UNITS'] == 'inches' and \
                    responses['HEIGHT_CM']:
                md[1][barcode]['HEIGHT_CM'] = \
                    2.54*md[1][barcode]['HEIGHT_CM']
            md[1][barcode]['HEIGHT_UNITS'] = 'centimeters'

            # Correct weight units
            if responses['WEIGHT_UNITS'] == 'pounds' and \
                    responses['WEIGHT_KG']:
                md[1][barcode]['WEIGHT_KG'] = \
                    md[1][barcode]['WEIGHT_KG']/2.20462
            md[1][barcode]['WEIGHT_UNITS'] = 'kilograms'

            # Get age in years (int) and remove birth month
            if responses['BIRTH_MONTH'] != 'Unspecified' and \
                    responses['BIRTH_YEAR'] != 'Unspecified':
                birthdate = datetime(
                    int(responses['BIRTH_YEAR']),
                    int(month_lookup[responses['BIRTH_MONTH']]),
                    1)
                now = datetime.now()
                md[1][barcode]['AGE_YEARS'] = int(self._months_between_dates(
                    birthdate, now) / 12.0)
            else:
                md[1][barcode]['AGE_YEARS'] = 'Unspecified'

            # GENDER to SEX
            sex = md[1][barcode]['GENDER']
            if sex is not None:
                sex = sex.lower()
            md[1][barcode]['SEX'] = sex

            # convenience variable
            site = barcode_info[barcode]['site_sampled']

            # Invariant information
            md[1][barcode]['ANONYMIZED_NAME'] = barcode
            md[1][barcode]['HOST_TAXID'] = 9606
            md[1][barcode]['TITLE'] = 'American Gut Project'
            md[1][barcode]['ALTITUDE'] = 0
            md[1][barcode]['ASSIGNED_FROM_GEO'] = 'Yes'
            md[1][barcode]['ENV_BIOME'] = 'ENVO:dense settlement biome'
            md[1][barcode]['ENV_FEATURE'] = 'ENVO:human-associated habitat'
            md[1][barcode]['DEPTH'] = 0

            # Sample-dependent information
            zipcode = md[1][barcode]['ZIP_CODE']
            country = barcode_info[barcode]['country']
            try:
                md[1][barcode]['LATITUDE'] = \
                    zip_lookup[zipcode][country][0]
                md[1][barcode]['LONGITUDE'] = \
                    zip_lookup[zipcode][country][1]
                md[1][barcode]['ELEVATION'] = \
                    zip_lookup[zipcode][country][2]
                md[1][barcode]['STATE'] = \
                    zip_lookup[zipcode][country][3]
                md[1][barcode]['COUNTRY'] = country_lookup[country]
            except KeyError:
                # geocode unknown zip/country combo and add to zipcode table & lookup dict
                if zipcode and country:
                    info = self.get_geocode_zipcode(zipcode, country)
                    zip_lookup[zipcode][country] = (info.lat, info.long, info.elev, info.city, info.state)
                else:
                    info = Location(None, None, None, None, None, None, None, None)
                md[1][barcode]['LATITUDE'] = '%.1f' % info.lat if info.lat else 'Unspecified'
                md[1][barcode]['LONGITUDE'] = '%.1f' % info.long if info.long else 'Unspecified'
                md[1][barcode]['ELEVATION'] = '%.1f' % info.elev if info.elev else 'Unspecified'
                md[1][barcode]['STATE'] = info.state if info.state else 'Unspecified'
                md[1][barcode]['COUNTRY'] = country_lookup[info.country] if info.country else 'Unspecified'

            md[1][barcode]['SURVEY_ID'] = survey_lookup[barcode]
            try:
                md[1][barcode]['TAXON_ID'] = md_lookup[site]['TAXON_ID']
            except Exception as e:
                print("BARCODE:", barcode, "  SITE:", site)
                raise e

            md[1][barcode]['COMMON_NAME'] = md_lookup[site]['COMMON_NAME']
            md[1][barcode]['COLLECTION_DATE'] = \
                barcode_info[barcode]['sample_date'].strftime('%m/%d/%Y')

            if barcode_info[barcode]['sample_time']:
                md[1][barcode]['COLLECTION_TIME'] = \
                    barcode_info[barcode]['sample_time'].strftime('%H:%M')
            else:
                # If no time data, show unspecified and default to midnight
                md[1][barcode]['COLLECTION_TIME'] = 'Unspecified'
                barcode_info[barcode]['sample_time'] = time(0, 0)

            md[1][barcode]['COLLECTION_TIMESTAMP'] = datetime.combine(
                barcode_info[barcode]['sample_date'],
                barcode_info[barcode]['sample_time']).strftime('%m/%d/%Y %H:%M')

            md[1][barcode]['ENV_MATTER'] = md_lookup[site]['ENV_MATTER']
            md[1][barcode]['SCIENTIFIC_NAME'] = md_lookup[site]['SCIENTIFIC_NAME']
            md[1][barcode]['SAMPLE_TYPE'] = md_lookup[site]['SAMPLE_TYPE']
            md[1][barcode]['BODY_HABITAT'] = md_lookup[site]['BODY_HABITAT']
            md[1][barcode]['BODY_SITE'] = md_lookup[site]['BODY_SITE']
            md[1][barcode]['BODY_PRODUCT'] = md_lookup[site]['BODY_PRODUCT']
            md[1][barcode]['HOST_COMMON_NAME'] = md_lookup[site]['COMMON_NAME']
            md[1][barcode]['HOST_SUBJECT_ID'] = md5(
                barcode_info[barcode]['ag_login_id'] +
                barcode_info[barcode]['participant_name']).hexdigest()
            if md[1][barcode]['WEIGHT_KG'] and md[1][barcode]['HEIGHT_CM']:
                md[1][barcode]['BMI'] = md[1][barcode]['WEIGHT_KG'] / \
                    (md[1][barcode]['HEIGHT_CM']/100)**2
            else:
                md[1][barcode]['BMI'] = ''
            md[1][barcode]['PUBLIC'] = 'Yes'

            #make sure conversions are done
            if md[1][barcode]['WEIGHT_KG']:
                md[1][barcode]['WEIGHT_KG'] = int(md[1][barcode]['WEIGHT_KG'])
            if md[1][barcode]['HEIGHT_CM']:
                md[1][barcode]['HEIGHT_CM'] = int(md[1][barcode]['HEIGHT_CM'])
            if md[1][barcode]['BMI']:
                md[1][barcode]['BMI'] = '%.2f' % md[1][barcode]['BMI']

            # Get rid of columns not wanted for pulldown
            del responses['BIRTH_MONTH']
            del md[1][barcode]['ABOUT_YOURSELF_TEXT']
            del md[1][barcode]['GENDER']
            del md[1][barcode]['ZIP_CODE']
            del md[1][barcode]['ANTIBIOTIC_MED']
            del md[1][barcode]['ANTIBIOTIC_CONDITION']
            del md[1][barcode]['CONDITIONS_MEDICATION']
            del md[1][barcode]['MEDICATION_LIST']
            del md[1][barcode]['SUPPLEMENTS']
            del md[1][barcode]['SPECIAL_RESTRICTIONS']
            del md[1][barcode]['WILLING_TO_BE_CONTACTED']

        return md

    def participant_names(self):
        """Retrieve the participant names for the given barcodes

        Returns
        -------
        list of tuple
            (barcode, participant name)
        """
        sql = """SELECT barcode, participant_name
                 FROM ag.ag_kit_barcodes
                 WHERE participant_name IS NOT NULL"""
        return self._con.execute_fetchall(sql)

    def pulldown(self, barcodes):
        """Pulls down AG metadata for given barcodes

        Parameters
        ----------
        barcodes : list of str
            Barcodes to pull metadata down for

        Returns
        -------
        metadata : dict of str
            Tab delimited qiita sample template, keyed to survey ID it came
            from
        failures : list of str
            Barcodes unable to pull metadata down for
        """
        all_survey_info = self.get_surveys(barcodes)
        if len(all_survey_info) == 0:
            # No barcodes given match any survey
            failures = set(barcodes)
            return {}, failures
        all_results = self.format_survey_data(all_survey_info)

        # keep track of which barcodes were seen so we know which weren't
        barcodes_seen = set()

        metadata = {}
        for survey, bc_responses in all_results.items():
            if not bc_responses:
                continue
            headers = sorted(bc_responses.values()[0])
            survey_md = [''.join(['sample_name\t', '\t'.join(headers)])]
            for barcode, shortnames_answers in sorted(bc_responses.items()):
                barcodes_seen.add(barcode)
                ordered_answers = [shortnames_answers[h] for h in headers]
                oa_hold = [barcode]
                for x in ordered_answers:
                    converted = str(x) if type(x) not in {str, unicode} else x
                    oa_hold.append(converted)
                survey_md.append('\t'.join(oa_hold))
            metadata[survey] = '\n'.join(survey_md)

        failures = sorted(set(barcodes) - barcodes_seen)

        return metadata, failures

    def _hash_password(self, password, hashedpw=None):
        """Hashes password

        Parameters
        ----------
        password: str
            Plaintext password
        hashedpw: str, optional
            Previously hashed password for bcrypt to pull salt from. If not
            given, salt generated before hash

        Returns
        -------
        str
            Hashed password

        Notes
        -----
        Relies on bcrypt library to hash passwords, which stores the salt as
        part of the hashed password. Don't need to actually store the salt
        because of this.
        """
        # all the encode/decode as a python 3 workaround for bcrypt
        if hashedpw is None:
            hashedpw = gensalt()
        else:
            hashedpw = hashedpw.encode('utf-8')
        password = password.encode('utf-8')
        output = hashpw(password, hashedpw)
        if isinstance(output, bytes):
            output = output.decode("utf-8")
        return output

    def authenticate_user(self, email, password):
        # see if user exists
        sql = """SELECT EXISTS (SELECT email FROM ag.labadmin_users
                 WHERE email = %s)"""
        exists = self._con.execute_fetchone(sql, [email])[0]

        if not exists:
            raise IncorrectEmailError("Email not valid: %s" % email)

        # pull password out of database
        sql = "SELECT password FROM ag.labadmin_users WHERE email = %s"

        # verify password
        dbpass = self._con.execute_fetchone(sql, [email])
        dbpass = dbpass[0] if dbpass else ''
        hashed = self._hash_password(password, dbpass)

        if hashed == dbpass:
            return True
        else:
            raise IncorrectPasswordError("Password not valid!")

        return False

    def getAGKitDetails(self, supplied_kit_id):
        sql = """SELECT
                 cast(ag_kit_id AS varchar(100)) AS ag_kit_id, supplied_kit_id,
                 kit_password, swabs_per_kit, kit_verification_code,
                 kit_verified, verification_email_sent
                 FROM ag_kit
                 WHERE supplied_kit_id = %s"""
        res = self._con.execute_fetchone(sql, [supplied_kit_id])
        if res is not None:
            return dict(res)
        else:
            return {}

    def add_barcodes_to_kit(self, ag_kit_id, num_barcodes=1):
        """Attaches barcodes to an existing american gut kit

        Parameters
        ----------
        ag_kit_id : str
            Kit ID to attach barcodes to
        num_barcodes : int, optional
            Number of barcodes to attach. Default 1

        Returns
        -------
        barcodes : list of str
            Barcodes attached to the kit
        """
        barcodes = self.get_unassigned_barcodes(num_barcodes)
        # assign barcodes to projects for the kit
        sql = """SELECT DISTINCT project_id FROM barcodes.project_barcode
                 JOIN ag.ag_kit_barcodes USING (barcode)
                 WHERE ag_kit_id = %s"""
        proj_ids = [x[0] for x in self._con.execute_fetchall(sql, [ag_kit_id])]
        barcode_project_insert = """INSERT INTO project_barcode
                                    (barcode, project_id)
                                    VALUES (%s, %s)"""
        project_inserts = []
        for barcode in barcodes:
            for project in proj_ids:
                project_inserts.append((barcode, project))
        self._con.executemany(barcode_project_insert, project_inserts)

        # Add barcodes to the kit
        sql = """INSERT  INTO ag_kit_barcodes
                (ag_kit_id, barcode, sample_barcode_file)
                VALUES (%s, %s, %s || '.jpg')"""
        barcode_info = [[ag_kit_id, b, b] for b in barcodes]
        self._con.executemany(sql, barcode_info)
        return barcodes

    def create_ag_kits(self, swabs_kits, tag=None, projects=None):
        """ Creates american gut handout kits on the database

        Parameters
        ----------
        swabs_kits : list of tuples
            kits and swab counts, with tuples in the form
            (# of swabs, # of kits with this swab count)
        tag : str, optional
            Tag to add to kit IDs. Default None
        projects : list of str, optional
            Subprojects to attach to, if given. Default None.

        Returns
        -------
        list of namedtuples
            The new kit information, in the form
            [(kit_id, password, verification_code, (barcode, barcode,...)),...]
        """
        # make sure we have enough barcodes
        total_swabs = sum(s * k for s, k in swabs_kits)
        barcodes = self.get_unassigned_barcodes(total_swabs)

        # Assign barcodes to AG and any other subprojects
        if projects is None:
            projects = ["American Gut Project"]
        else:
            if "American Gut Project" not in projects:
                projects.append("American Gut Project")
        self.assign_barcodes(total_swabs, projects)

        kits = []
        kit_barcode_inserts = []
        kit_inserts = []
        start = 0
        KitTuple = namedtuple('AGKit', ['kit_id', 'password',
                              'verification_code', 'barcodes'])
        # build the kits information and the sql insert information
        for num_swabs, num_kits in swabs_kits:
            kit_ids = make_valid_kit_ids(num_kits, self.get_used_kit_ids(),
                                         tag=tag)
            for i in range(num_kits):
                ver_code = make_verification_code()
                password = make_passwd()
                kit_bcs = tuple(barcodes[start:start + num_swabs])
                start += num_swabs
                kits.append(KitTuple(kit_ids[i], password, ver_code, kit_bcs))
                kit_inserts.append((kit_ids[i],
                                    self._hash_password(password),
                                    ver_code, num_swabs))
                for barcode in kit_bcs:
                    kit_barcode_inserts.append((kit_ids[i], barcode, barcode))

        # Insert kits, followed by barcodes attached to the kits
        kit_sql = """INSERT INTO ag_handout_kits
                     (kit_id, password, verification_code, swabs_per_kit)
                     VALUES (%s, %s, %s, %s)"""
        kit_barcode_sql = """INSERT INTO ag_handout_barcodes
                             (kit_id, barcode, sample_barcode_file)
                             VALUES(%s, %s, %s || '.jpg')"""

        self._con.executemany(kit_sql, kit_inserts)
        self._con.executemany(kit_barcode_sql, kit_barcode_inserts)

        return kits

    def get_used_kit_ids(self):
        """Grab in use kit IDs, return set of them
        """
        sql = """SELECT supplied_kit_id FROM ag_kit
                 UNION
                 SELECT kit_id from ag_handout_kits"""

        return set(i[0] for i in self._con.execute_fetchall(sql))

    def create_project(self, name):
        if name.strip() == '':
            raise ValueError("Project name can not be blank!")
        sql = "SELECT EXISTS(SELECT * FROM project WHERE project = %s)"
        exists = self._con.execute_fetchone(sql, [name])[0]
        if exists:
                raise ValueError("Project %s already exists!" % name)

        sql = """INSERT INTO project (project_id, project)
                 SELECT max(project_id)+1, %s FROM project"""
        self._con.execute(sql, [name])

    def get_unassigned_barcodes(self, n=None):
        """Returns unassigned barcodes

        Parameters
        ----------
        n : int, optional
            Number of barcodes to limit to, default returns all unused

        Returns
        -------
        list
            unassigned barcodes

        Raises
        ------
        ValueError
            Not enough unnasigned barcodes for n

        Notes
        -----
        Barcodes are returned in ascending order
        """
        sql_args = None
        sql = """SELECT DISTINCT barcode FROM barcodes.barcode
                 LEFT JOIN barcodes.project_barcode pb USING (barcode)
                 WHERE pb.barcode IS NULL
                 ORDER BY barcode ASC"""
        if n is not None:
            sql += " LIMIT %s"
            sql_args = [n]
        barcodes = [x[0] for x in self._con.execute_fetchall(sql, sql_args)]
        if len(barcodes) < n:
            raise ValueError("Not enough barcodes! %d asked for, %d remaining"
                             % (n, len(barcodes)))
        return barcodes

    def assign_barcodes(self, num_barcodes, projects):
        """Assign a given number of barcodes to projects

        Parameters
        ----------
        num_barcodes : int
            Number of barcodes to assign
        projects : list of str
            Projects to assgn barcodes to

        Returns
        -------
        list of str
            Barcodes assigned to the projects

        Raises
        ------
        ValueError
            One or more projects given don't exist in the database
        """
        # Verify projects given exist
        sql = "SELECT project FROM project"
        existing = {x[0] for x in self._con.execute_fetchall(sql)}
        not_exist = {p for p in projects if p not in existing}
        if not_exist:
            raise ValueError("Project(s) given don't exist in database: %s"
                             % ', '.join(not_exist))

        # Get unassigned barcode list and make sure we have enough barcodes
        barcodes = self.get_unassigned_barcodes(num_barcodes)

        # Assign barcodes to the project(s)
        sql = "SELECT project_id from project WHERE project in %s"
        proj_ids = [x[0] for x in
                    self._con.execute_fetchall(sql, [tuple(projects)])]

        barcode_project_insert = """INSERT INTO project_barcode
                                    (barcode, project_id)
                                    VALUES (%s, %s)"""
        project_inserts = []
        for barcode in barcodes:
            for project in proj_ids:
                project_inserts.append((barcode, project))
        self._con.executemany(barcode_project_insert, project_inserts)
        # Set assign date for the barcodes
        sql = """UPDATE barcodes.barcode
                 SET assigned_on = NOW() WHERE barcode IN %s"""
        self._con.execute(sql, [tuple(barcodes)])
        return barcodes

    def create_barcodes(self, num_barcodes):
        """Creates new barcodes

        Parameters
        ----------
        num_barcodes : int
            Number of barcodes to create

        Returns
        -------
        list
            New barcodes created
        """

        # Get newest barcode as an integer
        sql = "SELECT max(barcode::integer) from barcode"
        newest = self._con.execute_fetchone(sql)[0]

        # create new barcodes by padding integers with zeros
        barcodes = ['%09d' % b for b in range(newest+1, newest+1+num_barcodes)]

        barcode_insert = """INSERT INTO barcode (barcode, obsolete)
                            VALUES (%s, 'N')"""
        self._con.executemany(barcode_insert, [[b] for b in barcodes])
        return barcodes

    def get_barcodes_for_projects(self, projects, limit=None):
        """Gets barcode information for barcodes belonging to projects

        Parameters
        ----------
        projects : list of str
            Projects to get barcodes for (if multiple given, intersection of
            barcodes in each project is returned)
        limit : int, optional
            Number of barcodes to return, starting with most recent
            (defult all)

        Returns
        -------
        list of dict
            each barcode with information
        """
        select_sql = """SELECT barcode, create_date_time, sample_postmark_date,
                        scan_date,status,sequencing_status,biomass_remaining,
                        obsolete,array_agg(project) AS projects
                        FROM barcode
                        JOIN project_barcode USING (barcode)
                        JOIN project USING (project_id)
                        WHERE project IN %s GROUP BY barcode
                        ORDER BY barcode DESC"""
        sql_args = [tuple(projects)]
        if limit is not None:
            select_sql += " LIMIT %s"
            sql_args.append(limit)
        return self._con.execute_fetchall(select_sql, sql_args)

    def add_external_survey(self, survey, description, url):
        """Adds a new external survey to the database

        Parameters
        ----------
        survey : str
            Name of the external survey
        description : str
            Short description of what the survey is about
        url : str
            URL for the external survey
        """
        sql = """INSERT INTO ag.external_survey_sources
                 (external_survey, external_survey_description,
                  external_survey_url)
                 VALUES (%s, %s, %s)
                 RETURNING external_survey_id"""
        return self._con.execute_fetchone(sql, [survey, description, url])[0]

    def store_external_survey(self, in_file, survey, pulldown_date=None,
                              separator="\t", survey_id_col="survey_id"):
        """Stores third party survey answers in the database

        Parameters
        ----------
        in_file : str
            Filepath to the survey answers spreadsheet
        survey : str
            What third party survey this belongs to
        pulldown_date : datetime object, optional
            When the data was pulled from the external source, default now()
        separator : str, optional
            What separator is used, default tab
        survey_id_col : str
            What column header holds the associated user AG survey id
            Default 'survey_id'

        Raises
        ------
        ValueError
            Survey passed is not found
        """
        # Get the external survey ID
        sql = """SELECT external_survey_id
                 FROM external_survey_sources
                 WHERE external_survey = %s"""
        external_id = self._con.execute_fetchall(sql, [survey])
        if not external_id:
            raise ValueError("Unknown external survey: %s" % survey)
        external_id = external_id[0]
        if pulldown_date is None:
            pulldown_date = datetime.now()

        # Load file data into insertable json format
        inserts = []
        with open(in_file) as f:
            header = f.readline().strip().split('\t')
            for line in f:
                line = line.strip()
                hold = {h: v.strip() for h, v in zip(header, line.split('\t'))}
                sid = hold[survey_id_col]
                del hold[survey_id_col]
                inserts.append([sid, external_id, pulldown_date, json.dumps(hold)])

        # insert into the database
        sql = """INSERT INTO ag.external_survey_answers
                 (survey_id, external_survey_id, pulldown_date, answers)
                 VALUES (%s, %s, %s, %s)"""
        self._con.executemany(sql, inserts)

    def get_external_survey(self, survey, survey_ids, pulldown_date=None):
        """Get the answers to a survey for given survey IDs

        Parameters
        ----------
        survey : str
            Survey to retrieve answers for
        survey_ids : list of str
            AG survey ids to retrieve answers for
        pulldown_date : datetime object, optional
            Specific pulldown date to limit answers to, default None

        Returns
        -------
        dict of dicts
            Answers to the survey keyed to the given survey IDs, in the form
            {survey_id: {header1: answer, header2: answer, ...}, ...}

        Notes
        -----
        If there are multiple pulldowns for a given survey_id, the newest one
        will be returned.
        """
        # Do pulldown of ids and answers, ordered so newest comes out last
        # This allows you to not specify pulldown date and still get newest
        # answers for the survey
        sql = """SELECT survey_id, answers FROM
                 (SELECT * FROM ag.external_survey_answers
                 JOIN ag.external_survey_sources USING (external_survey_id)
                 WHERE external_survey = %s{0}
                 ORDER BY pulldown_date ASC)"""
        sql_args = [survey]
        format_str = ""
        if pulldown_date is not None:
            format_str = " AND pulldown_date = %s "
            sql_args.append(pulldown_date)

        return {s: json.loads(a)
                for s, a in self._con.execute_fetchall(
                    sql.format(format_str), sql_args)}

    def addAGLogin(self, email, name, address, city, state, zip_, country):
        clean_email = email.strip().lower()
        sql = "select ag_login_id from ag_login WHERE LOWER(email) = %s"
        ag_login_id = self._con.execute_fetchone(sql, [clean_email])
        if not ag_login_id:
            # create the login
            sql = ("INSERT INTO ag_login (email, name, address, city, state, "
                   "zip, country) VALUES (%s, %s, %s, %s, %s, %s, %s) "
                   "RETURNING ag_login_id")
            ag_login_id = self._con.execute_fetchone(
                sql, [clean_email, name, address, city, state, zip_, country])
        return ag_login_id[0]

    def updateAGLogin(self, ag_login_id, email, name, address, city, state,
                      zipcode, country):
        sql = """UPDATE  ag_login
                SET email = %s, name = %s, address = %s, city = %s, state = %s,
                    zip = %s, country = %s
                WHERE ag_login_id = %s"""
        self._con.execute(sql, [email.strip().lower(), name,
                                address, city, state, zipcode, country,
                                ag_login_id])

    def updateAGKit(self, ag_kit_id, supplied_kit_id, kit_password,
                    swabs_per_kit, kit_verification_code):
        kit_password = hashpw(kit_password)
        sql = """UPDATE ag_kit
                 SET supplied_kit_id = %s, kit_password = %s,
                     swabs_per_kit = %s, kit_verification_code = %s
                 WHERE ag_kit_id = %s"""

        self._con.execute(sql, [supplied_kit_id, kit_password, swabs_per_kit,
                                kit_verification_code, ag_kit_id])

    def updateAGBarcode(self, barcode, ag_kit_id, site_sampled,
                        environment_sampled, sample_date, sample_time,
                        participant_name, notes, refunded, withdrawn):
        sql = """UPDATE  ag_kit_barcodes
                 SET ag_kit_id = %s, site_sampled = %s, environment_sampled = %s,
                     sample_date = %s, sample_time = %s, participant_name = %s,
                     notes = %s, refunded = %s, withdrawn = %s
                 WHERE barcode = %s"""
        self._con.execute(sql, [ag_kit_id, site_sampled, environment_sampled,
                                sample_date, sample_time, participant_name,
                                notes, refunded, withdrawn, barcode])

    def AGGetBarcodeMetadata(self, barcode):
        results = self._con.execute_proc_return_cursor(
            'ag_get_barcode_metadata', [barcode])
        rows = results.fetchall()
        results.close()

        return [dict(row) for row in rows]

    def AGGetBarcodeMetadataAnimal(self, barcode):
        results = self._con.execute_proc_return_cursor(
            'ag_get_barcode_md_animal', [barcode])
        rows = results.fetchall()
        results.close()

        return [dict(row) for row in rows]

    def get_geocode_zipcode(self, zipcode, country):
        """Adds geocode information to zipcode table if needed and return info

        Parameters
        ----------
        zipcode : str
            Zipcode to geocode
        country : str, optional
            Country zipcode belongs in. Default infer from zipcode. Useful
            for countries with zipcode formated like USA

        Returns
        -------
        info : NamedTuple
            Location namedtuple in form
            Location('zip', 'lat', 'long', 'elev', 'city', 'state', 'country')

        Notes
        -----
        If the tuple contains nothing but the zipcode and None for all other
        fields, no geocode was found. Zipcode/country combination added as
        'cannot_geocode'
        """
        # Catch sending None or empty string for these
        if not zipcode or not country:
            return Location(zipcode, None, None, None, None, None, None, country)

        sql = """SELECT round(latitude::numeric, 1), round(longitude::numeric, 1),
                    round(elevation::numeric, 1), city, state, zipcode, country
                 FROM ag.zipcodes
                 WHERE zipcode = %s and country = %s"""
        zip_info = self._con.execute_fetchone(sql, [zipcode, country])
        if zip_info:
            zip_info = [zipcode] + zip_info
            return Location(*zip_info)

        info = geocode('%s %s' % (zipcode, country))
        cannot_geocode = False
        # Clean the zipcode so it is same case and setup, since international
        # people can enter lowercased zipcodes or missing spaces, and google
        # does not give back 9 digit zipcodes for USA, only 6.
        clean_postcode = str(info.postcode).lower().replace(' ', '')
        clean_zipcode = str(zipcode).lower().replace(' ', '').split('-')[0]
        if not info.lat:
            cannot_geocode = True
        # Use startswith because UK zipcodes can be 2, 3, or 6 characters
        elif info.country != country or not clean_postcode.startswith(clean_zipcode):
            # countries and zipcodes dont match, so blank out info
            info = Location(zipcode, None, None, None, None, None, None, country)
            cannot_geocode = True
        sql = """INSERT INTO ag.zipcodes
                    (zipcode, latitude, longitude, elevation, city,
                     state, country, cannot_geocode)
                 VALUES (%s,%s,%s,%s,%s,%s,%s, %s)"""
        self._con.execute(sql, [zipcode, info.lat, info.long, info.elev,
                                info.city, info.state, country, cannot_geocode])
        return info

    def addGeocodingInfo(self, limit=None, retry=False):
        """Adds latitude, longitude, and elevation to ag_login_table

        Uses the city, state, zip, and country from the database to retrieve
        lat, long, and elevation from the google maps API.

        If any of that information cannot be retrieved, then cannot_geocode
        is set to 'y' in the ag_login table, and it will not be tried again
        on subsequent calls to this function.  Pass retry=True to retry all
        (or maximum of limit) previously failed geocodings.
        """

        # clear previous geocoding attempts if retry is True
        if retry:
            sql = """UPDATE  ag_login
                     SET latitude = %s, longitude = %s, elevation = %s, cannot_geocode = %s
                     WHERE ag_login_id IN (
                        SELECT ag_login_id FROM ag_login
                        WHERE cannot_geocode = 'y')"""
            self._con.execute(sql)

        # get logins that have not been geocoded yet
        sql = """SELECT city, state, zip, country,
                     cast(ag_login_id as varchar(100))
                FROM ag_login
                WHERE elevation is NULL AND cannot_geocode is NULL"""
        logins = self._con.execute_fetchall(sql)

        row_counter = 0
        sql_args = []
        for city, state, zipcode, country, ag_login_id in logins:
            row_counter += 1
            if limit is not None and row_counter > limit:
                break

            # Attempt to geocode
            address = '{0} {1} {2} {3}'.format(city, state, zipcode, country)
            try:
                info = geocode(address)
                # empty string to indicate geocode was successful
                sql_args.append([info.lat, info.long, info.elev, '', ag_login_id])
            except GoogleAPILimitExceeded:
                # limit exceeded so no use trying to keep geocoding
                break
            except:
                # Catch ANY other error and set to could not geocode
                sql_args.append([None, None, None, 'y', ag_login_id])

        sql = """UPDATE  ag_login
                 SET latitude = %s, longitude = %s, elevation = %s, cannot_geocode = %s
                 WHERE ag_login_id = %s"""
        self._con.executemany(sql, sql_args)

    def getGeocodeStats(self):
        stat_queries = [
            ("Total Rows",
             "select count(*) from ag_login"),
            ("Cannot Geocode",
             "select count(*) from ag_login where cannot_geocode = 'y'"),
            ("Null Latitude Field",
             "select count(*) from ag_login where latitude is null"),
            ("Null Elevation Field",
             "select count(*) from ag_login where elevation is null")
        ]
        results = []
        for name, sql in stat_queries:
            total = self._con.execute_fetchone(sql)[0]
            results.append((name, total))
        return results

    def getAGStats(self):
        # returned tuple consists of:
        # site_sampled, sample_date, sample_time, participant_name,
        # environment_sampled, notes
        stats_list = [
            ('Total handout kits', 'SELECT count(*) FROM ag.ag_handout_kits'),
            ('Total handout barcodes', 'SELECT count(*) FROM ag.ag_handout_barcodes'),
            ('Total consented participants', 'SELECT count(*) FROM ag.ag_consent'),
            ('Total registered kits', 'SELECT count(*) FROM ag.ag_kit'),
            ('Total registered barcodes', 'SELECT count(*) FROM ag.ag_kit_barcodes'),
            ('Total barcodes with results', "SELECT count(*) FROM ag.ag_kit_barcodes WHERE results_ready = 'Y'"),
            ('Average age of participants', """SELECT AVG(AGE((yr.response || '-' ||
                                                CASE mo.response
                                                    WHEN 'January' THEN '1'
                                                    WHEN 'February' THEN '2'
                                                    WHEN 'March' THEN '3'
                                                    WHEN 'April' THEN '4'
                                                    WHEN 'May' THEN '5'
                                                    WHEN 'June' THEN '6'
                                                    WHEN 'July' THEN '7'
                                                    WHEN 'August' THEN '8'
                                                    WHEN 'September' THEN '9'
                                                    WHEN 'October' THEN '10'
                                                    WHEN 'November' THEN '11'
                                                    WHEN 'December' THEN '12'
                                                  END || '-1')::date
                                                )) FROM
                                              (SELECT response, survey_id FROM ag.survey_answers WHERE survey_question_id = 112) AS yr
                                              JOIN
                                              (SELECT response, survey_id FROM ag.survey_answers WHERE survey_question_id = 111) AS mo USING (survey_id)
                                              WHERE yr.response != 'Unspecified' AND mo.response != 'Unspecified'"""),
            ('Total male participants', "SELECT count(*) FROM ag.survey_answers WHERE survey_question_id = 107 AND response = 'Male'"),
            ('Total female participants', "SELECT count(*) FROM ag.survey_answers WHERE survey_question_id = 107 AND response = 'Female'")
            ]
        stats = []
        for label, sql in stats_list:
            res = self._con.execute_fetchone(sql)[0]
            if type(res) == timedelta:
                res = str(res.days/365) + " years"
            stats.append((label, res))
        return stats

    def updateAKB(self, barcode, moldy, overloaded, other, other_text,
                  date_of_last_email):
        """ Update ag_kit_barcodes table.
        """
        sql_args = [moldy, overloaded, other, other_text]
        update_date = ''
        if date_of_last_email:
            update_date = ', date_of_last_email = %s'
            sql_args.append(date_of_last_email)
        sql_args.append(barcode)

        sql = """UPDATE  ag_kit_barcodes
                 SET moldy = %s, overloaded = %s, other = %s,
                     other_text = %s{}
                 WHERE barcode = %s""".format(update_date)
        self._con.execute(sql, sql_args)

    def updateBarcodeStatus(self, status, postmark, scan_date, barcode,
                            biomass_remaining, sequencing_status, obsolete):
        """ Updates a barcode's status
        """
        sql = """update  barcode
        set     status = %s,
            sample_postmark_date = %s,
            scan_date = %s,
            biomass_remaining = %s,
            sequencing_status = %s,
            obsolete = %s
        where   barcode = %s"""
        self._con.execute(sql, [status, postmark, scan_date, biomass_remaining,
                                sequencing_status, obsolete, barcode])

    def get_barcode_survey(self, barcode):
        """Return survey ID attached to barcode"""
        sql = """SELECT DISTINCT ags.survey_id FROM ag.ag_kit_barcodes
                 JOIN ag.survey_answers USING (survey_id)
                 JOIN ag.group_questions gq USING (survey_question_id)
                 JOIN ag.surveys ags USING (survey_group)
                 WHERE barcode = %s"""
        res = self._con.execute_fetchone(sql, [barcode])
        return res[0] if res else None

    def search_participant_info(self, term):
        sql = """select   cast(ag_login_id as varchar(100)) as ag_login_id
                 from    ag_login al
                 where   lower(email) like %s or lower(name) like
                 %s or lower(address) like %s"""
        liketerm = '%%' + term.lower() + '%%'
        results = self._con.execute_fetchall(sql, [liketerm, liketerm, liketerm])
        return [x[0] for x in results]

    def search_kits(self, term):
        sql = """ select  cast(ag_login_id as varchar(100)) as ag_login_id
                 from    ag_kit
                 where   lower(supplied_kit_id) like %s or
                 lower(kit_password) like %s or
                 lower(kit_verification_code) = %s"""
        liketerm = '%%' + term.lower() + '%%'
        results = self._con.execute_fetchall(sql, [liketerm, liketerm, liketerm])
        return [x[0] for x in results]

    def search_barcodes(self, term):
        sql = """select  cast(ak.ag_login_id as varchar(100)) as ag_login_id
                 from    ag_kit ak
                 inner join ag_kit_barcodes akb
                 on ak.ag_kit_id = akb.ag_kit_id
                 where   barcode like %s or lower(participant_name) like
                 %s or lower(notes) like %s"""
        liketerm = '%%' + term.lower() + '%%'
        results = self._con.execute_fetchall(sql, [liketerm, liketerm, liketerm])
        return [x[0] for x in results]

    def get_kit_info_by_login(self, ag_login_id):
        sql = """SELECT  cast(ag_kit_id as varchar(100)) as ag_kit_id,
                        cast(ag_login_id as varchar(100)) as ag_login_id,
                        supplied_kit_id, kit_password, swabs_per_kit,
                        kit_verification_code, kit_verified
                FROM    ag_kit
                WHERE   ag_login_id = %s"""
        info = self._con.execute_fetchdict(sql, [ag_login_id])
        return info if info else []

    def search_handout_kits(self, term):
        sql = """SELECT kit_id, password, barcode, verification_code
                 FROM ag.ag_handout_kits
                 JOIN (SELECT kit_id, barcode, sample_barcode_file
                    FROM ag.ag_handout_barcodes
                    GROUP BY kit_id, barcode) AS hb USING (kit_id)
                 WHERE kit_id LIKE %s or barcode LIKE %s"""
        liketerm = '%%' + term + '%%'
        return self._con.execute_fetchdict(sql, [liketerm, liketerm])

    def get_login_by_email(self, email):
        sql = """select name, address, city, state, zip, country, ag_login_id
                 from ag_login where email = %s"""
        row = self._con.execute_fetchone(sql, [email])

        login = {}
        if row:
            login = dict(row)
            login['email'] = email

        return login

    def get_login_info(self, ag_login_id):
        sql = """SELECT  ag_login_id, email, name, address, city, state, zip,
                         country
                 FROM    ag_login
                 WHERE   ag_login_id = %s"""
        return self._con.execute_fetchdict(sql, [ag_login_id])

    def getAGBarcodeDetails(self, barcode):
        sql = """SELECT  email, cast(ag_kit_barcode_id as varchar(100)),
                    cast(ag_kit_id as varchar(100)), barcode,  site_sampled,
                    environment_sampled, sample_date, sample_time,
                    participant_name, notes, refunded, withdrawn, moldy, other,
                    other_text, date_of_last_email ,overloaded, name, status
                 FROM ag_kit_barcodes akb
                 JOIN ag_kit USING(ag_kit_id)
                 JOIN ag_login USING (ag_login_id)
                 JOIN barcode USING(barcode)
                 WHERE barcode = %s"""

        results = self._con.execute_fetchone(sql, [barcode])
        if not results:
            return {}
        else:
            return dict(results)

    def get_barcode_info_by_kit_id(self, ag_kit_id):
        sql = """SELECT  cast(ag_kit_barcode_id as varchar(100)) as
                  ag_kit_barcode_id, cast(ag_kit_id as varchar(100)) as
                  ag_kit_id, barcode, sample_date, sample_time, site_sampled,
                  participant_name, environment_sampled, notes, results_ready,
                  withdrawn, refunded
                FROM    ag_kit_barcodes
                WHERE   ag_kit_id = %s"""

        results = [dict(row) for row in self._con.execute_fetchall(sql, [ag_kit_id])]
        return results

    def getHumanParticipants(self, ag_login_id):
        # get people from new survey setup
        sql = """SELECT DISTINCT participant_name from ag.ag_login_surveys
                 JOIN ag.survey_answers USING (survey_id)
                 JOIN ag.group_questions gq USING (survey_question_id)
                 JOIN ag.surveys ags USING (survey_group)
                 WHERE ag_login_id = %s AND ags.survey_id = %s"""
        results = self._con.execute_fetchall(sql, [ag_login_id, 1])
        return [row[0] for row in results]

    def getAGKitsByLogin(self):
        sql = """SELECT  lower(al.email) as email, supplied_kit_id,
                cast(ag_kit_id as varchar(100)) as ag_kit_id
                FROM ag_login al
                INNER JOIN ag_kit USING (ag_login_id)
                ORDER BY lower(email), supplied_kit_id"""
        rows = self._con.execute_fetchall(sql)
        return [dict(row) for row in rows]

    def getAnimalParticipants(self, ag_login_id):
        sql = """SELECT DISTINCT participant_name from ag.ag_login_surveys
                 JOIN ag.survey_answers USING (survey_id)
                 JOIN ag.group_questions gq USING (survey_question_id)
                 JOIN ag.surveys ags USING (survey_group)
                 WHERE ag_login_id = %s AND ags.survey_id = %s"""
        return [row[0] for row in self._con.execute_fetchall(
                    sql, [ag_login_id, 2])]

    def ag_new_survey_exists(self, barcode):
        """
        Returns metadata for an american gut barcode in the new database
        tables
        """
        sql = "SELECT EXISTS(SELECT * from ag_kit_barcodes WHERE barcode = %s)"
        return self._con.execute_fetchone(sql, [barcode])[0]

    def get_plate_for_barcode(self, barcode):
        """
        Gets the sequencing plates a barcode is on
        """
        sql = """select  p.plate, p.sequence_date
                 from    plate p inner join plate_barcode pb on
                 pb.plate_id = p.plate_id \
                where   pb.barcode = %s"""

        return [dict(row) for row in self._con.execute_fetchall(sql, [barcode])]

    def getBarcodeProjType(self, barcode):
        """ Get the project type of the barcode.
            Return a tuple of projects and parent project.
        """
        sql = """SELECT project from barcodes.project
                 JOIN barcodes.project_barcode USING (project_id)
                 where barcode = %s"""
        results = [x[0] for x in self._con.execute_fetchall(sql, [barcode])]
        if 'American Gut Project' in results:
            parent_project = 'American Gut'
            projects = ', '.join(results)
        else:
            projects = ', '.join(results)
            parent_project = projects
        return (projects, parent_project)

    def setBarcodeProjects(self, barcode, add_projects=None, rem_projects=None):
        """Sets the projects barcode is associated with

        Parameters
        ----------
        barcode : str
            Barcode to update
        add_projects : list of str, optional
            List of projects from projects table to add project to
        rem_projects : list of str, optional
            List of projects from projects table to remove barcode from
        """
        if add_projects:
            sql = """INSERT INTO barcodes.project_barcode
                      SELECT project_id, %s FROM (
                        SELECT project_id from barcodes.project
                        WHERE project in %s)
                     AS P"""

            self._con.execute(sql, [barcode, tuple(add_projects)])
        if rem_projects:
            sql = """DELETE FROM barcodes.project_barcode
                     WHERE barcode = %s AND project_id IN (
                       SELECT project_id FROM barcodes.project WHERE project IN %s)"""
            self._con.execute(sql, [barcode, tuple(rem_projects)])

    def getProjectNames(self):
        """Returns a list of project names
        """
        sql = """SELECT project FROM project"""
        return [x[0] for x in self._con.execute_fetchall(sql)]
