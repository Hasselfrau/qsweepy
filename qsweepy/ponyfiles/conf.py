CONNECT_DB = {'host':"localhost", 
              'database':'qsweepy', 
              'user':'qsweepy', 
              'password':'qsweepy'}

LOGS_INSERTION_QUERY = """INSERT INTO Logs (
                               id,
                               log_type, 
                               tag, 
                               time_stamp) 
                         VALUES (
                               %(id)s,
                               %(levelname)s, 
                               %(msg)s, 
                               %(dbtime)s
                               );"""

LOGS_INITIAL_QUERY =  """CREATE TABLE IF NOT EXISTS Logs (
                        id int,
                        log_type text,
                        tag text,
                        time_stamp text
                   )"""
