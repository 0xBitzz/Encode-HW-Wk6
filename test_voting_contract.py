import time
import pytest
from contract import Vote
from beaker import sandbox
from beaker.client import ApplicationClient
from beaker.client.api_providers import AlgoNode, Network
from algosdk.atomic_transaction_composer import AccountTransactionSigner, TransactionWithSigner
from algosdk.transaction import AssetTransferTxn


@pytest.fixture(scope="module")
def create_app():
    global app_client
    global creator_acct
    global accounts
    global app

    accounts = sandbox.get_accounts()
    creator_acct = accounts.pop()
    app = Vote()

    app_client = ApplicationClient(client=sandbox.get_algod_client(), app=app, signer=creator_acct.signer)
    app_id, app_addr, txid= app_client.create()
    
    app_client.fund(amt=1_000_000, addr=app_addr)

@pytest.fixture(scope="module")
def create_asset():
    global asset_id
    app_client.call(app.create_asset, asset_name="ENB", total_supply=1_000_000)
    asset_id = app_client.get_application_state()['asset_id']

@pytest.fixture(scope="module")
def account1_opt_in_to_asset():
    global acct1
    global acct1_client

    sp = app_client.get_suggested_params()

    acct1 = accounts.pop()
    acct1_client = app_client.prepare(signer=acct1.signer)

    txn = TransactionWithSigner(
        txn=AssetTransferTxn(sender=acct1.address, sp=sp, receiver=acct1.address, amt=0, index=asset_id),
        signer=acct1.signer
    )
    acct1_client.call(app.optin_asset, txn=txn)

@pytest.fixture(scope="module")
def account2_opt_in_to_asset():
    global acct2
    global acct2_client

    sp = app_client.get_suggested_params()

    acct2 = accounts.pop()
    acct2_client = app_client.prepare(signer=acct2.signer)

    txn = TransactionWithSigner(
        txn=AssetTransferTxn(sender=acct2.address, sp=sp, receiver=acct2.address, amt=0, index=asset_id),
        signer=acct2.signer
    )
    acct2_client.call(app.optin_asset, txn=txn)

@pytest.fixture(scope="module")
def check_acct1_bal():
    global acct1_bal
    acct1_bal = acct1_client.call(app.get_asset_bal, account=acct1.address)

@pytest.fixture(scope="module")
def transfer_asset_to_account1():
    app_client.call(app.transfer_asset, receiver=acct1.address, amount=1_000)

@pytest.fixture(scope="module")
def transfer_asset_to_account2():
    app_client.call(app.transfer_asset, receiver=acct2.address, amount=2_000)

@pytest.fixture(scope="module")
def account1_register():
    acct1_client.opt_in()

@pytest.fixture(scope="module")
def account2_register():
    acct2_client.opt_in()

@pytest.mark.create
def test_initial_aid(create_app):
    assert app_client.get_application_state()["asset_id"] == 0

@pytest.mark.create
def test_initial_vote_count(create_app):
    assert app_client.get_application_state()["vote_count"] == 0

@pytest.mark.create_asset
def test_asset_created(create_app, create_asset):
    assert app_client.get_application_state() != 0

@pytest.mark.first_optin
def test_account1_to_opt_in_asset(create_app, create_asset, account1_opt_in_to_asset):
    assert acct1_client.call(app.get_asset_bal, account=acct1.address).return_value == 0

@pytest.mark.first_transfer
def test_transfer_asset_to_acct1(create_app, create_asset, account1_opt_in_to_asset, transfer_asset_to_account1):
    assert acct1_client.call(app.get_asset_bal, account=acct1.address).return_value == 1_000

@pytest.mark.second_optin
def test_account2_to_opt_in_asset(create_app, create_asset, account2_opt_in_to_asset):
    assert acct2_client.call(app.get_asset_bal, account=acct2.address).return_value == 0

@pytest.mark.second_transfer
def test_transfer_asset_to_acct2(create_app, create_asset, account2_opt_in_to_asset, transfer_asset_to_account2):
    assert acct2_client.call(app.get_asset_bal, account=acct2.address).return_value == 2_000

