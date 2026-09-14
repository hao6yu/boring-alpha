"""Render a static research figure from the completed conditional account."""
from datetime import date
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import StrMethodFormatter

from diagnostic_io import HERE, RAW


def run():
    ledgers=json.loads((RAW/'account-ledgers.json').read_text())
    base=ledgers['base']['nonroutine']; stress=ledgers['stress']['nonroutine']
    dates=[date.fromisoformat(d['date']) for d in base['daily']]
    elapsed=[(d-dates[0]).days+1 for d in dates]
    low=[10000*1.04**(n/365) for n in elapsed]
    high=[10000*1.06**(n/365) for n in elapsed]
    fig,ax=plt.subplots(figsize=(10,4.8),layout='constrained')
    ax.fill_between(dates,low,high,color='#dfe8df',label='4–6% constant cash-rate scenarios')
    ax.plot(dates,[float(d['nav']) for d in base['daily']],color='#2456a6',lw=1.8,label='Insider account: base costs')
    ax.plot(dates,[float(d['nav']) for d in stress['daily']],color='#b94b43',lw=1.4,label='Insider account: stressed costs')
    ax.axhline(10000,color='#999999',lw=.7,ls=':')
    ax.axvline(date(2023,1,1),color='#aaaaaa',lw=.7,ls='--')
    ax.text(date(2023,2,1),9250,'Both accounts halted in Dec 2022\nCash earns 0% afterward',fontsize=9,color='#494949')
    ax.set_title('$10,000 insider-purchase diagnostic',loc='left',fontsize=15,fontweight='bold')
    ax.set_ylabel('Account NAV (USD)')
    ax.yaxis.set_major_formatter(StrMethodFormatter('${x:,.0f}'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4)); ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax.grid(axis='y',alpha=.2); ax.spines[['top','right']].set_visible(False)
    ax.legend(loc='upper left',frameon=False,fontsize=8)
    fig.supxlabel('Jan 2022–Dec 2023 • Identifiable subset only; four signal-price gaps and incomplete controls\nModeled fills, before tax; includes locked dividend claims. Not independent validation.',fontsize=8,color='#555555')
    fig.savefig(HERE/'account-nav.png',dpi=170)
    plt.close(fig)


if __name__=='__main__': run()
