'''
Created on Jul 30, 2020

@author: paepcke
'''
import unittest
import sqlite3
import os, sys

sys.path.append(os.path.join(os.path.dirname(__file__), '.'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from elephant_utils.sqlite_db_merger import SqliteDbMerger

TEST_ALL = True
#TEST_ALL = False


class TestSqliteMerger(unittest.TestCase):

    #------------------------------------
    # setUpClass 
    #-------------------
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.samples_create_cmd = '''
                CREATE TABLE Samples (
                    sample_id INTEGER PRIMARY KEY,
                    char_col varchar(10),
                    float_col float
                    )
                '''
        cls.other_table_create_cmd = '''
                CREATE TABLE OtherTable (
                    dir_or_file varchar(100)
                    )
                '''

    #------------------------------------
    # setUp 
    #-------------------

    def setUp(self):
        
        self.curr_dir = os.path.dirname(__file__)

        # Destination db:
        self.dst_db_path = os.path.join(self.curr_dir, 
                                        'dst_db.sqlite')
        if os.path.exists(self.dst_db_path):
            os.remove(self.dst_db_path)
        self.dst_db = sqlite3.connect(self.dst_db_path)
        self.dst_db.row_factory = sqlite3.Row
        
        self.dst_db.execute("DROP TABLE IF EXISTS Samples;")
        self.dst_db.execute("DROP TABLE IF EXISTS OtherTable;")

        # Source db 1:
        self.src_db1_path = os.path.join(self.curr_dir, 
                                         'src_db1.sqlite')
        if os.path.exists(self.src_db1_path):
            os.remove(self.src_db1_path)
        self.src_db1 = sqlite3.connect(self.src_db1_path)
        self.src_db1.row_factory = sqlite3.Row
        # Make the Samples tbl in db1:
        self.src_db1.execute(self.samples_create_cmd)
        
        # Put something into db1's Sample table:
        self.src_db1.execute('''
                INSERT INTO Samples (sample_id,
                                     char_col,
                                     float_col)
                          VALUES (0,'foo',10.0),
                                 (1,'bar',20.0);
                ''')
        self.src_db1.commit()
        
        # Source db 2:
        self.src_db2_path = os.path.join(self.curr_dir, 'src_db2.sqlite')
        if os.path.exists(self.src_db2_path):
            os.remove(self.src_db2_path)
        self.src_db2 = sqlite3.connect(self.src_db2_path)
        self.src_db2.row_factory = sqlite3.Row

        # Create Samples and Other table:
        self.src_db2.execute(self.samples_create_cmd)
        self.src_db2.execute(self.other_table_create_cmd)

        # Put something into db2's Sample, and Other table:
        self.src_db2.execute('''
                INSERT INTO Samples (sample_id,
                                     char_col,
                                     float_col)
                          VALUES (2,'blue',30.0),
                                 (3,'green',40.0);
                        ''')
        self.src_db2.commit()

        self.src_db2.execute('''
                INSERT INTO OtherTable (dir_or_file)
                          VALUES ('/oak/blossom.jpg'),
                                 ('/linde/laurel/thorn.jpg'),
                                 ('/alder/berry/fruit.jpg');
                        ''')
        self.dst_db.close()
        self.src_db1.close()
        self.src_db2.close()

    #------------------------------------
    # tearDown 
    #-------------------

    def tearDown(self):
        os.remove(self.dst_db_path)
        os.remove(self.src_db1_path)
        os.remove(self.src_db2_path)

    #------------------------------------
    # testOneTableTwoSrcDbs 
    #-------------------

    @unittest.skipIf(TEST_ALL != True, 'skipping temporarily')
    def testOneTableTwoSrcDbs(self):
        SqliteDbMerger([self.src_db1_path, self.src_db2_path],
                       self.dst_db_path,
                       tables=['Samples'])

        self.connect_all_dbs()
        
        self.assertCopies([self.src_db1, self.src_db2],
                          self.dst_db, 
                          ['Samples']
                          )

    #------------------------------------
    # testTwoTablesTwoSrcDbs 
    #-------------------
    
    @unittest.skipIf(TEST_ALL != True, 'skipping temporarily')
    def testTwoTablesTwoSrcDbs(self):
        SqliteDbMerger([self.src_db1_path, self.src_db2_path],
                       self.dst_db_path,
                       tables=['Samples', 'OtherTable'])

        self.connect_all_dbs()
        self.assertCopies([self.src_db1, self.src_db2],
                          self.dst_db, 
                          ['Samples', 'OtherTable']
                          )

    #------------------------------------
    # testAllTables
    #-------------------
    
    @unittest.skipIf(TEST_ALL != True, 'skipping temporarily')
    def testAllTables(self):
        SqliteDbMerger([self.src_db1_path, self.src_db2_path],
                       self.dst_db_path
                       )

        self.connect_all_dbs()
        self.assertCopies([self.src_db1, self.src_db2],
                          self.dst_db, 
                          ['Samples', 'OtherTable']
                          )

    #------------------------------------
    # testTwoTablesTwoSrcDbsPrimKeyConflict 
    #-------------------
    
    @unittest.skipIf(TEST_ALL != True, 'skipping temporarily')
    def testTwoTablesTwoSrcDbsPrimKeyConflict(self):
        
        # Make db2 have the same vals for 
        # sample_id as db1:
        self.connect_all_dbs()
        self.src_db2.execute('''
                UPDATE Samples 
                  SET sample_id = 0
                WHERE sample_id = 2;
                ''')
        
        self.src_db2.execute('''
                UPDATE Samples 
                  SET sample_id = 1
                WHERE sample_id = 3;
                ''')

        SqliteDbMerger([self.src_db1_path, self.src_db2_path],
                       self.dst_db_path,
                       tables=['Samples', 'OtherTable'],
                       verbose=True
                       )

        self.connect_all_dbs()
        rows = self.dst_db.execute('''
                SELECT sample_id from Samples;
                ''').fetchall()
        sample_ids = [row['sample_id'] for row in rows]
        
        # assertCountEqual() ensures that 
        # all elements of second are in 
        # first, though order is unimportant:

        self.assertCountEqual(sample_ids, [0,1,2,3])


    #------------------------------------
    # testDstTblPreExisting
    #-------------------
    
    @unittest.skipIf(TEST_ALL != True, 'skipping temporarily')
    def testDstTblPreExisting(self):
        
        # Make db2 have the same vals for 
        # sample_id as db1:
        self.connect_all_dbs()
        self.src_db2.execute('''
                UPDATE Samples 
                  SET sample_id = 0
                WHERE sample_id = 2;
                ''')
        
        self.src_db2.execute('''
                UPDATE Samples 
                  SET sample_id = 1
                WHERE sample_id = 3;
                ''')

        # Make dst table pre-existing:
        self.dst_db.execute(self.samples_create_cmd)

        SqliteDbMerger([self.src_db1_path, self.src_db2_path],
                       self.dst_db_path,
                       tables=['Samples', 'OtherTable'])

        self.connect_all_dbs()
        rows = self.dst_db.execute('''
                SELECT sample_id from Samples;
                ''').fetchall()
        sample_ids = [row['sample_id'] for row in rows]
        
        # assertCountEqual() ensures that 
        # all elements of second are in 
        # first, though order is unimportant:

        self.assertCountEqual(sample_ids, [0,1,2,3])

# ---------------- Utilities --------------

    #------------------------------------
    # assertCopies 
    #-------------------
    
    def assertCopies(self, src_dbs, dst_db, table_names):

        # Number of rows in Samples table in each
        # src db:
        
        # Build skeleton result struct:
        #   {<db_obj1> : {tbl1 : [],
        #                 tbl2 : [],
        #                     ...
        #                }
        #   {<db_obj2> : {tbl1 : [],
        #                 tbl2 : [],
        #                     ...
        #                }
        
        all_dbs = src_dbs.copy()
        all_dbs.append(dst_db)
        sample_rows = {}
        for db in all_dbs:
            sample_rows[db] = {}
            for tbl_nm in table_names:
                sample_rows[db][tbl_nm] = []
        
        # Fill the None's with sqlite results (query result cursors)
        # that are ready for content checking: 
        for db in all_dbs:
            for src_tbl_nm in table_names:
                try:
                    sample_rows[db][src_tbl_nm] = \
                        db.execute(f'''
                            select * from {src_tbl_nm};
                        ''').fetchall()
                except sqlite3.OperationalError as e:
                    # Normal to have some tables only
                    # present in some src dbs but not others:
                    if e.args[0].find("no such table") > -1:
                        continue
                        

        # Now the assertion fest:
        for tbl_nm in table_names:
            dst_db_rows  = sample_rows[dst_db][tbl_nm]
            all_src_rows = []
            for src_db in src_dbs:
                all_src_rows.extend(sample_rows[src_db][tbl_nm])
            
            # Dst db's tbl must have all the src db's 
            # rows in tbl_nm:
            self.assertEqual(len(dst_db_rows), len(all_src_rows))
            # Rows in dst db in curr tbl must
            # be same as union of all rows in 
            # corresponding tables in src dbs.
            # assertCountEqual() ensures that 
            # all elements of second are in 
            # first, though order is unimportant:

            self.assertTrue(self.find_rows_match(dst_db_rows, all_src_rows))

    #------------------------------------
    # find_rows_match
    #-------------------

    def find_rows_match(self, rowsA, rowsB, verbose=True):
        '''
        Given two lists of db rows that conform
        to the dict API, return True if
        the two sets of rows match pairwise.
        
        @param rowsA: list of db rows
        @type rowsA: [sqlite3.Row]
        @param rowsB: list of db rows
        @type rowsB: [sqlite3.Row]
        '''
        for rowA in rowsA:
            comparisons = [True if self.rows_equal(rowA,rowB, verbose=verbose)
                            else False
                            for rowB in rowsB]
            if sum(comparisons) > 0:
                # Found match for curr el of rowsA:
                continue
            else:
                if verbose:
                    print(f"samples_id {rowA['sample_id']} in rowsA has no partner")
                return False
        return True
    
    #------------------------------------
    # rows_equal 
    #-------------------

    def rows_equal(self, row1, row2, verbose=False):
        '''
        Return True if the two db rows 
        match by content. Assumes that rows
        conform to dict API
        
        @param row1:
        @type row1:
        @param row2:
        @type row2:
        '''
        for col_name in row1.keys():
            if row1[col_name] != row2[col_name]:
                if verbose:
                    print(f"Column name {col_name}: {row1[col_name]} vs. {row2[col_name]}")
                return False
        return True

    #------------------------------------
    # connect_all_dbs 
    #-------------------
    
    def connect_all_dbs(self):
        self.dst_db = sqlite3.connect(self.dst_db_path)
        self.dst_db.row_factory = sqlite3.Row

        self.src_db1 = sqlite3.connect(self.src_db1_path)
        self.src_db1.row_factory = sqlite3.Row
        
        self.src_db2 = sqlite3.connect(self.src_db2_path)
        self.src_db2.row_factory = sqlite3.Row

# ------------------ Main ----------------


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
