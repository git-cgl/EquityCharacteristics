# Calculate HSZ Replicating Anomalies
# SUE: Standardized Unexpected Earnings (Earnings surprise)

import pandas as pd
import numpy as np
import datetime as dt
import wrds
import psycopg2
from dateutil.relativedelta import *
from pandas.tseries.offsets import *
from pandasql import *

###################
# Connect to WRDS #
###################
conn=wrds.Connection()

###################
# Compustat Block #
###################
comp = conn.raw_sql("""
                        select gvkey, datadate, fyearq, fqtr, epspxq, ajexq
                        from comp.fundq
                        where indfmt = 'INDL' 
                        and datafmt = 'STD'
                        and popsrc = 'D'
                        and consol = 'C'
                        and datadate >= '01/01/1959'
                        """)

comp['datadate'] = pd.to_datetime(comp['datadate'])

###################
#    CCM Block    #
###################
ccm = conn.raw_sql("""
                  select gvkey, lpermno as permno, linktype, linkprim, 
                  linkdt, linkenddt
                  from crsp.ccmxpf_linktable
                  where linktype in ('LU', 'LC')
                  """)

ccm['linkdt'] = pd.to_datetime(ccm['linkdt'])
ccm['linkenddt'] = pd.to_datetime(ccm['linkenddt'])
# if linkenddt is missing then set to today date
ccm['linkenddt'] = ccm['linkenddt'].fillna(pd.to_datetime('today'))

ccm1 = pd.merge(comp, ccm, how='left', on=['gvkey'])

# set link date bounds
ccm2 = ccm1[(ccm1['datadate']>=ccm1['linkdt']) & (ccm1['datadate']<=ccm1['linkenddt'])]
ccm2 = ccm2[['gvkey', 'permno', 'datadate', 'fyearq', 'fqtr', 'epspxq', 'ajexq']]

# the time series of exspxq/ajexq
ccm2['eps'] = ccm2['epspxq']/ccm2['ajexq']
ccm2.drop_duplicates(['permno', 'datadate'], inplace=True)

# merge lag1 to lag9, then calculate stand deviation
ccm2 = ccm2[ccm2['eps'].notna()]
ccm2['count'] = ccm2.groupby('permno').cumcount() + 1
ccm2.sort_values(by=['permno', 'datadate'], inplace=True)

ccm2['e1'] = np.where(ccm2['permno'] == ccm2['permno'].shift(1), ccm2['eps'].shift(1), np.nan)
ccm2['e2'] = np.where(ccm2['permno'] == ccm2['permno'].shift(2), ccm2['eps'].shift(2), np.nan)
ccm2['e3'] = np.where(ccm2['permno'] == ccm2['permno'].shift(3), ccm2['eps'].shift(3), np.nan)
ccm2['e4'] = np.where(ccm2['permno'] == ccm2['permno'].shift(4), ccm2['eps'].shift(4), np.nan)
ccm2['e5'] = np.where(ccm2['permno'] == ccm2['permno'].shift(5), ccm2['eps'].shift(5), np.nan)
ccm2['e6'] = np.where(ccm2['permno'] == ccm2['permno'].shift(6), ccm2['eps'].shift(6), np.nan)
ccm2['e7'] = np.where(ccm2['permno'] == ccm2['permno'].shift(7), ccm2['eps'].shift(7), np.nan)
ccm2['e8'] = np.where(ccm2['permno'] == ccm2['permno'].shift(8), ccm2['eps'].shift(8), np.nan)

condlist = [ccm2['count']<=6,
            ccm2['count']==7,
            ccm2['count']==8,
            ccm2['count']>=9]
choicelist = [np.nan,
              ccm2[['e8', 'e7', 'e6', 'e5', 'e4', 'e3']].std(axis=1),
              ccm2[['e8', 'e7', 'e6', 'e5', 'e4', 'e3', 'e2']].std(axis=1),
              ccm2[['e8', 'e7', 'e6', 'e5', 'e4', 'e3', 'e2', 'e1']].std(axis=1)]
ccm2['sue_std'] = np.select(condlist, choicelist, default=np.nan)

ccm2['sue'] = (ccm2['eps'] - ccm2['e4'])/ccm2['sue_std']

# populate the quarterly sue to monthly
crsp_msf = conn.raw_sql("""
                        select distinct date
                        from crsp.msf
                        where date >= '01/01/1959'
                        """)

ccm2['datadate'] = pd.to_datetime(ccm2['datadate'])
ccm2['plus12m'] = ccm2['datadate'] + np.timedelta64(12, 'M')
ccm2['plus12m'] = ccm2['plus12m'] + MonthEnd(0)

df = sqldf("""select a.*, b.date
              from ccm2 a left join crsp_msf b 
              on a.datadate <= b.date
              and a.plus12m >= b.date
              order by a.permno, b.date, a.datadate desc;""", globals())

df = df.drop_duplicates(['permno', 'date'])
df['datadate'] = pd.to_datetime(df['datadate'])
df = df[['gvkey', 'permno', 'datadate', 'date', 'sue']]

####### test ######
df['date'] = pd.to_datetime(df['date'])
df['yearend'] = df['date'] + YearEnd(0)
df1 = df[df['yearend']>='2017-12-31']