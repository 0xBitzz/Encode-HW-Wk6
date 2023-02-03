from typing import Final
from pyteal import *
from beaker import (
    Application,
    ApplicationStateValue,
    AccountStateValue,
    Authorize,
    bare_external,
    external,
    internal,
    create,
    opt_in
)


class Vote(Application):
    asset_id: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Asset ID"
    )

    is_registered: Final[AccountStateValue] = AccountStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Flag to know if an account can vote or not, 1 - True, 0 - False"
    )
    vote_amount: Final[AccountStateValue] = AccountStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Amount an account holds at voting time"
    )
    vote_choice: Final[AccountStateValue] = AccountStateValue(
        stack_type=TealType.bytes,
        default=Bytes(""),
        descr="Choice made by this account, can be either of yes, no, abstain"
    )

    vote_count: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="The accumulated number of votes"
    )
    reg_begin: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64, descr="Registration window begin time"
    )
    reg_end: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64, descr="Registration window end time"
    )
    vote_begin: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64, descr="Voting window start time"
    )
    vote_end: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64, descr="Voting window end time"
    )

    MIN_VOTE_AMOUNT = Int(1_000)
    FEE = Int(1_000)

    # Asset
    @external(authorize=Authorize.only(Global.creator_address()))
    def create_asset(self, asset_name: abi.String, total_supply: abi.Uint64):
        return Seq(
            Assert(self.asset_id == Int(0)),
            InnerTxnBuilder.Execute(
                {
                    TxnField.type_enum: TxnType.AssetConfig,
                    TxnField.config_asset_name: asset_name.get(),
                    TxnField.config_asset_total: total_supply.get(),
                    TxnField.config_asset_manager: self.address,
                    TxnField.fee: self.FEE
                }
            ),
            self.asset_id.set(InnerTxn.created_asset_id())
        )

    @external
    def optin_asset(
        self,
        txn: abi.AssetTransferTransaction,
        aid: abi.Asset = asset_id  # type: ignore[assignment]
    ):
        return Seq(
            Assert(
                txn.get().sender() == Txn.sender(),
                txn.get().asset_amount() == Int(0),
                txn.get().asset_receiver() == Txn.sender(),
                txn.get().xfer_asset() == self.asset_id
            )
        )

    @external(authorize=Authorize.only(Global.creator_address()))
    def transfer_asset(
        self,
        receiver: abi.Account,
        amount: abi.Uint64,
        aid: abi.Asset = asset_id  # type: ignore[assignment]
    ):
        return Seq(
            (bal := AssetHolding.balance(account=self.address, asset=self.asset_id)),
            Assert(
                And(
                    amount.get() > Int(0),
                    amount.get() <= bal.value(),
                ),
                comment="Ensure amount is valid",
            ),
            InnerTxnBuilder.Execute(
                {
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: self.asset_id,
                    TxnField.asset_amount: amount.get(),
                    TxnField.asset_receiver: receiver.address(),
                    TxnField.fee: self.FEE
                }
            )
        )

    @external
    def get_asset_bal(
        self,
        account: abi.Account,
        asset_id: abi.Asset = asset_id,  # type: ignore[assignment]
        *,
        output: abi.Uint64
    ):
        return Seq(
            (
                bal := AssetHolding.balance(
                    account=account.address(), asset=self.asset_id
                )
            ),
            output.set(bal.value())
        )

    @external(read_only=True)
    def get_asset_id(self, *, output: abi.Uint64):
        return output.set(self.asset_id.get())

    # Vote
    @create
    def create(self):
        return self.initialize_application_state()

    @opt_in
    def register(self):
        return Seq(
            Assert(
                Global.latest_timestamp() >= self.reg_begin,
                Global.latest_timestamp() <= self.reg_end,
            ),
            self.initialize_account_state(),
            self.is_registered.set(Int(1))
        )

    @external(authorize=Authorize.only(Global.creator_address()))
    def setup(
        self,
        reg_begin: abi.Uint64,
        reg_end: abi.Uint64,
        vote_begin: abi.Uint64,
        vote_end: abi.Uint64
    ):
        return Seq(
            self.reg_begin.set(Global.latest_timestamp() + reg_begin.get()),
            self.reg_end.set(Global.latest_timestamp() + reg_end.get()),
            self.vote_begin.set(Global.latest_timestamp() + vote_begin.get()),
            self.vote_end.set(Global.latest_timestamp() + vote_end.get())
        )

    @external(authorize=Authorize.opted_in())
    def cast_vote(self, choice: abi.String, asset_id: abi.Asset = asset_id):
        return Seq(
            (bal := AssetHolding.balance(account=Txn.sender(), asset=self.asset_id)),
            Assert(self.is_registered.get() == Int(1)),
            Assert(
                And(
                    Global.latest_timestamp() >= self.vote_begin.get(),
                    Global.latest_timestamp() <= self.vote_end.get()
                )
            ),
            Assert(
                And(
                    bal.hasValue(),
                    bal.value() >= self.MIN_VOTE_AMOUNT
                )
            ),
            (amt := abi.Uint64()).set(bal.value()),
            Assert(
                Or(
                    choice.get() == Bytes("yes"),
                    choice.get() == Bytes("no"),
                    choice.get() == Bytes("abstain")
                )
            ),
            self.vote_choice.set(choice.get()),
            If(choice.get() == Bytes("yes"), self.upvote(amount=amt))
        )

    @internal
    def upvote(self, amount: abi.Uint64):
        return Seq(
            self.vote_amount.set(amount.get()),
            self.vote_count.set(self.vote_count + self.vote_amount)
        )

    @bare_external(close_out=CallConfig.CALL)
    def clear_vote(self):
        return Seq(
            If(self.vote_choice.get() == Bytes("yes"))
            .Then(
                self.vote_count.set(self.vote_count - self.vote_amount),
                self.vote_amount.set(Int(0))
            ),
            self.vote_choice.set(Bytes(""))
        )


if __name__ == "__main__":
    Vote().dump("./artifacts")
