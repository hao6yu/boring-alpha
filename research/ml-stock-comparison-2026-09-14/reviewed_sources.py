"""Source-reviewed lifecycle and action facts, fixed before model fitting."""
SPLITS={
 ('FAST','2019-05-23'):{'ratio':2,'source':'https://investor.fastenal.com/stock-info/dividend-history/default.aspx'},
 ('EW','2020-06-01'):{'ratio':3,'source':'https://ir.edwards.com/resources/investor-faqs/stock-split-faqs/default.aspx'},
 ('MCHP','2021-10-13'):{'ratio':2,'source':'https://ir.microchip.com/stock-data/stock-split-history'},
}
SPINS={
 ('WYN','2018-06-01'):{'child':'WH','ratio':1,'source':'https://investor.travelandleisureco.com/company-info/company-separation','effective_time_source':'https://investor.travelandleisureco.com/sec-filings/all-sec-filings/content/0001047469-18-003865/a2235744zex-99_1.htm'},
 ('ZBH','2022-03-01'):{'child':'ZIMV','ratio':.1,'source':'https://investor.zimmerbiomet.com/news-and-events/news/archive/03-01-2022-120035502'},
 ('DOV','2018-05-09'):{'child':'CHX','original_child_symbol':'APY','ratio':.5,'source':'https://www.sec.gov/Archives/edgar/data/29905/000002990519000057/dov-20190930.htm','child_alias_source':'https://www.sec.gov/Archives/edgar/data/1723089/000119312520159803/d857405dex991.htm'},
 ('DXC','2018-06-01'):{'child':'PRSP','ratio':.5,'source':'https://www.sec.gov/Archives/edgar/data/1688568/000168856818000054/dxcuspsseparation8-k.htm'},
 ('VFC','2019-05-23'):{'child':'KTB','ratio':1/7,'source':'https://www.vfc.com/investors/news-events-presentations/press-releases/detail/1682/vf-corporation-approves-separation-of-kontoor-brands-inc'},
 ('IP','2021-10-01'):{'child':'SLVM','ratio':1/11,'source':'https://internationalpaper2022rd.q4web.com/news/news-details/2021/International-Paper-Company-Announces-Completion-of-Sylvamo-Corporation-Spin-Off/default.aspx'},
}
CASH_OVERRIDES={
 ('LYB','2019-01-14'):{'amount':0,'reason':'The $15 distribution belongs to A. Schulman convertible special stock, not LYB common.',
                         'source':'https://www.lyondellbasell.com/en/news-events/corporate--financial-news/a.-schulman-inc2.-a-lyondellbasell-subsidiary-announces-convertible-special-stock-dividend',
                         'crosscheck':'https://investors.lyondellbasell.com/stock-info/Dividend-History/'},
 ('LYB','2022-06-03'):{'amount':6.39,'payment_date':'2022-06-13','reason':'$5.20 special plus $1.19 ordinary dividend, both for common shareholders.',
                         'source':'https://www.lyondellbasell.com/en/news-events/corporate--financial-news/lyondellbasell-announces-%245.20-special-dividend-and-increases-quarterly-dividend-by-5-percent'},
}
# Removed cohort stocks remain in the inventory but cannot be repurchased as
# the old issuer. Cash outcomes are separate from exchange execution prices.
LIFECYCLE={
 'FOXA':{'end':'2019-03-19','outcome':'MIXED_MERGER_AND_DISTRIBUTION_BEFORE_FIRST_SIGNAL',
          'source':'https://thewaltdisneycompany.com/press-releases/disney-21st-century-fox-acquisition-closing-date/',
          'provider_series_rejected':'Tiingo FOXA starts March 2019 and is the newly separated Fox Corporation, not the 2018 cohort issuer.'},
 'ESRX':{'end':'2018-12-20','outcome':'MERGER_BEFORE_FIRST_SIGNAL', 'source':'https://www.sec.gov/Archives/edgar/data/1532063/000114036118045477/form8k.htm'},
 'RHT':{'end':'2019-07-08','event_date':'2019-07-09','cash':190,'outcome':'CASH_MERGER','source':'https://www.ibm.com/investor/news/ibm-completes-acquisition-of-red-hat'},
 'XEC':{'end':'2021-09-30','event_date':'2021-10-01','child':'CTRA','ratio':4.0146,'outcome':'STOCK_MERGER','source':'https://www.sec.gov/Archives/edgar/data/858470/000085847022000009/cog-20211231.htm'},
 'KSU':{'end':'2021-12-13','event_date':'2021-12-14','cash':90,'child':'CP','ratio':2.884,'outcome':'CASH_AND_STOCK_MERGER','source':'https://www.sec.gov/Archives/edgar/data/54480/000119312521356252/d25745d8k.htm'},
 'CERN':{'end':'2022-06-07','event_date':'2022-06-08','cash':95,'outcome':'CASH_MERGER','source':'https://www.nasdaqtrader.com/TraderNews.aspx?id=eca2022-127'},
 'DISCK':{'end':'2022-04-08','event_date':'2022-04-11','outcome':'SHARE_CLASS_REORGANIZATION_REQUIRES_NEW_CLASS_EVIDENCE','source':'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2022-63'},
}
ALIASES={
 'BLL':{'provider':'BALL','source':'https://www.ball.com/newswire/article/124123/ball-board-declares-quarterly-dividend-stock-ticker-symbol-changing-to-ball'},
 'ANTM':{'provider':'ELV','source':'https://www.elevancehealth.com/newsroom/elevance-health-rings-in-rebrand-with-nyse-opening-bell'},
 'CTL':{'provider':'LUMN','source':'https://ir.lumen.com/news/news-details/2020/CenturyLink-Transforms-Rebrands-as-Lumen/default.aspx'},
 'WYN':{'provider':'TNL','source':'https://investor.travelandleisureco.com/company-info/faq'},
}
