import psycopg2
import time
import logging
from conf import *
from datetime import datetime, timezone

class psqlHandler(logging.Handler):
    '''
    Logging handler for PostgreSQL.
    '''
    initial_sql = LOGS_INITIAL_QUERY
    sql_insretion = LOGS_INSERTION_QUERY

    def __init__(self, params):

        if not params:
            raise Exception("No database where to log")

        self.__database = params['database']
        self.__host = params['host']
        self.__user = params['user']
        self.__password = params['password']

        self.__connect = None

        if not self.connect():
            raise Exception("Database connection error, no logging")

        logging.Handler.__init__(self)

        self.__connect.cursor().execute(psqlHandler.initial_sql)
        self.__connect.commit()
        self.__connect.cursor().close()

    def formatDBTime(self, record):
        record.dbtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))

    def connect(self):
        try:
            self.__connect = psycopg2.connect(
                database=self.__database,
                host=self.__host,
                user=self.__user,
                password=self.__password,
                sslmode="disable")

            return True
        except:
            return False

    def get_log_id(self, cur):
        """
        Get last log id from DB and return increment it
        """

        get_last_id = """SELECT id
                                 FROM Logs
                                 ORDER by id desc
                                 LIMIT 1"""

        cur.execute(get_last_id)
        last_id = cur.fetchone()[0]
        if not last_id:
            last_id = 0
        return last_id + 1


    def emit(self, record):

        # Use default formatting:
        self.format(record)
        # Set the database time up:
        self.formatDBTime(record)

        if record.exc_info:
            record.exc_text = logging._defaultFormatter.formatException(record.exc_info)
        else:
            record.exc_text = ""

        # Insert log record:
        try:
            cur = self.__connect.cursor()
        except:
            self.connect()
            cur = self.__connect.cursor()

        self.id = self.get_log_id(cur)
        record.id = self.id
        cur.execute(psqlHandler.sql_insretion, record.__dict__)

        self.__connect.commit()
        self.__connect.cursor().close()
