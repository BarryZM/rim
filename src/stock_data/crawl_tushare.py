from typing import List, NoReturn, Tuple, Iterator
import sched, time
from itertools import groupby, product, count
import datetime

import pandas as pd
import sqlalchemy
import tushare as ts

from src import config
from src.stock_data import rim_db

ts.set_token(config.ts_token)


def get_securities():
    pro = ts.pro_api()
    # 查询当前所有正常上市交易的股票列表
    return pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')


def tushare_indicator_to_db(index: int, codes: List[str]) -> NoReturn:
    indicators: List[dict] = []
    print(f"第{index}批次 {datetime.datetime.now()}")
    for code in codes:
        print(f"{code}")
        indicator: pd.DataFrame = pro.fina_indicator(ts_code=code, period='20181231', fields='ts_code, eps, bps')
        if indicator.empty is False:
            indicators.append(indicator.iloc[0].to_dict())
    pd.DataFrame(indicators).to_sql('indicator2018', con=sqlalchemy.create_engine('sqlite:///../../data/ts.db'),
                                    if_exists= 'replace' if index == 0 else 'append', chunksize=1024)


def save_ts_indicator_to_db(code_year_lst: List[Tuple[str, str]]) -> NoReturn:
    """ 根据指定的股票代码，从tushare获取财务指标数据，并保存到本地数据库
    假设：
    1. 数据库路径为项目路径 \data\ts.db
    2. 数据表为financial_indicator
    3. 字段名称同tushare规定 https://tushare.pro/document/2?doc_id=79
    输入假设：
    codes 代码-年列表，代码和年份都要要符合tushare的格式要求。列表不能为空
    输出：
    NoReturn
    """
    assert code_year_lst is not None
    indicators: List[dict] = []
    for (code, year), index in code_year_lst:
        print(f"{index}, {code}, {year}")
        indicator: pd.DataFrame = ts.pro_api().fina_indicator(ts_code=code, period=year)
        if indicator.empty is False:
            indicators.append(indicator.iloc[0].to_dict())
    pd.DataFrame(indicators).to_sql('financial_indicator', con=sqlalchemy.create_engine('sqlite:///../../data/ts.db'),
                                    if_exists='append', chunksize=1024)
    print("Save to DB")


def task_scheduler() -> NoReturn:
    pro = ts.pro_api()
    s = sched.scheduler(time.time, time.sleep)
    securities: pd.DataFrame = pro.stock_basic(exchange='', list_status='L', fields='ts_code')
    securities_lst: List[str] = [t.ts_code for t in securities.itertuples()]
    code_year_set = set(product(securities_lst, [f"{y}1231" for y in range(2010, 2019)]))

    today = datetime.datetime.now()
    today = today.strftime("%Y-%m-%d")
    financial_indicators = rim_db.get_financial_indicator(today)
    code_set = financial_indicators.index
    done_code_year_set = set(zip(code_set.get_level_values(0), code_set.get_level_values(1)))

    to_do_set = code_year_set - done_code_year_set
    to_do_with_index = zip(to_do_set, count())

    job_groups = groupby(to_do_with_index, key=lambda x: x[1]//36)      # 每30秒查询-保存36条记录
    for i, jobs in job_groups:
        s.enter(i * 30, 1, save_ts_indicator_to_db, kwargs={'code_year_lst': [j for j in jobs]})
    s.run()


if __name__ == '__main__':
    task_scheduler()
