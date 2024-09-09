#import cx_Oracle --> import module
#con = cx_Oracle.connect('username/password@localhost') ---> connect to DB
#cusor = con.cursore() --> Cursor object to execute SQL query and provide results; i.e. pointer
#cursor.executeman(sqlquerys) --> to execute a signle query with multiple bind variables
#commit() --> for DML CRUM submission
#fetchone() --> fetch one signle row from top of the result set
#fetchmany(int) --> fetch a limited number of rows based on the argument
#fetchall() --> fetch all rows from the result set
#cursor.callproc() --> calls procedure
#close() ----> Mandatory <-------- closes connection
  #cursor.close()
  #con.close()

################################## EXAMPLE #############################################
'''
import cxOracle as db
try:
  connection = db.connect('username/password@localhost')
except db.DatabaseError as err:
  log(err)
else:
  try:
    cursor = connection.cursor()
    # Use bind variables ? or strictly filter parameters
    # Otherwise allows for SQLi & SHi attacks
    query = f'''
    select s.status,p.file_uri from product_file p, product_file_site_map s where p.product_file_intid=s.product_file_intid and s.site_name like "%{self.kafka_topic}%"
    '''
    cursor.execute(query)
    rows = cursor.fetchall()
    for row in rows:
      status, uri = row
      log('{}:{}'.format(status,uri))

    except db.DatabaseErorr as error:
      log(error)
    finally:
      if cursor:
        cursor.close()
  finally:
    if connection:
      connection.close()

'''
