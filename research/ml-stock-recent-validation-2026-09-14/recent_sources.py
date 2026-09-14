"""New source-supported events; original source ledger remains unchanged."""
NEW_SPLITS = {
    ('AVGO','2024-07-15'): {'ratio':10,'source':'https://investors.broadcom.com/news-releases/news-release-details/broadcom-inc-announces-second-quarter-fiscal-year-2024-financial'},
    ('TSCO','2024-12-20'): {'ratio':5,'source':'https://corporate.tractorsupply.com/newsroom/news-releases/news-releases-details/2025/Tractor-Supply-Company-Reports-Fourth-Quarter-and-Fiscal-Year-2024-Financial-Results-Provides-Fiscal-Year-2025-Outlook/default.aspx'},
    ('FAST','2025-05-22'): {'ratio':2,'source':'https://www.sec.gov/Archives/edgar/data/815556/000081555625000085/ex_991042325stocksplitpres.htm'},
    ('ORLY','2025-06-10'): {'ratio':15,'source':'https://corporate.oreillyauto.com/wp-content/uploads/2025/07/2025-Stock-Split-FAQ.pdf'},
}
NEW_SPINS = {
    ('APTV','2026-04-01'): {'child':'VGNT','ratio':1/3,'source':'https://www.sec.gov/Archives/edgar/data/2078008/000119312526138219/d52176dex991.htm'},
}
NEW_LIFECYCLE = {
    'SEE': {'end':'2026-04-08','event_date':'2026-04-09','cash':42.15,'outcome':'CASH_MERGER','source':'https://sealedair.gcs-web.com/news-releases/news-release-details/sealed-air-announces-completion-acquisition-cdr','qualification':'Issuer announcement at 08:36 EDT states the acquisition is complete and NYSE trading has ceased. The provider row dated April 9 is excluded; exact broker cash-credit timing is not asserted.'},
    'PXD': {'end':'2024-05-02','event_date':'2024-05-03','child':'XOM','ratio':2.3234,'outcome':'STOCK_MERGER','source':'https://www.sec.gov/Archives/edgar/data/34088/000095010324006322/dp210867_ex9901.htm','ratio_source':'https://infomemo.theocc.com/infomemos?number=54543'},
    'LEG': {'end':'2026-08-25','event_date':'2026-08-26','child':'SGI','ratio':.1455,'outcome':'STOCK_MERGER','source':'https://somnigroup.com/newsroom/news-details/2026/Somnigroup-Completes-Combination-with-Leggett--Platt/default.aspx','filing_source':'https://www.sec.gov/Archives/edgar/data/1206264/000120626426000121/sgi-20260826.htm'},
}
REGISTRANT_BRIDGES = {
    'BLK': {'old':'0001364742','new':'0002012383','effective':'2024-10-01','ratio':1,
            'source':'https://www.sec.gov/Archives/edgar/data/2012383/000095017025026584/blk-20241231.htm',
            'selection':'Use old reports before reorganization, then combine only matching source concepts with filing availability cutoffs; conflicting equal-date facts stay unavailable.'},
}
