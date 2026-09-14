from insider_rules import classify, common_stock, disclosure_day, linked_footnotes, positive


def trade(day, public=None):
    return {'transaction_date': day, 'disclosure_day': public or day}


def test_missing_history_never_becomes_nonroutine():
    assert classify([trade('2021-04-01')], 2022) == 'UNKNOWN_INSUFFICIENT_YEARS'


def test_only_known_trades_before_year_start_can_classify():
    known = [trade('2019-01-02'), trade('2020-02-03'), trade('2021-03-04')]
    assert classify(known, 2022) == 'NONROUTINE'
    later = [trade('2020-01-03', '2022-02-01'), trade('2021-01-04', '2022-02-01')]
    assert classify(known + later, 2022) == 'NONROUTINE'
    earlier = [trade('2020-01-03'), trade('2021-01-04')]
    assert classify(known + earlier, 2022) == 'ROUTINE'


def test_rolling_rule_does_not_retain_old_routine_status():
    history = [trade('2019-01-02'), trade('2020-01-03'), trade('2021-01-04'), trade('2022-06-01')]
    assert classify(history, 2022) == 'ROUTINE'
    assert classify(history, 2023) == 'NONROUTINE'


def test_history_conflict_blocks_label_in_relevant_year():
    history = [trade('2019-01-02'), trade('2020-01-03'), trade('2021-01-04')]
    assert classify(history, 2022, [2020]) == 'UNKNOWN_HISTORY'


def test_timestamp_requires_full_contract_and_conservative_date():
    assert disclosure_day({'acceptanceDatetime':'20230105193219','filingDate':'20230106'}) == '2023-01-06'
    import pytest
    with pytest.raises(ValueError):
        disclosure_day({'acceptanceDatetime':'2023-01-05T19:32:19Z','filingDate':'20230105'})


def test_footnote_references_and_instrument_filters():
    text, missing = linked_footnotes({'transactionSharesFn':'F1 F2','natureOfOwnershipFn':'F1'}, {'F1':'One shared note'})
    assert text == 'One shared note' and missing == ['F2']
    assert common_stock('Class A Common Stock')
    assert not common_stock('Option to acquire common stock')
    assert not common_stock('Common Units')
    assert positive('0.01') and not positive('NaN') and not positive('')
