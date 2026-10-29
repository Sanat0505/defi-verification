"""Reviewed operation semantics; ABI presence is not transaction permission."""

LENDING_DOC = "https://aave.com/docs/aave-v3/smart-contracts/pool"
UMBRELLA_DOC = "https://aave.com/docs/aave-v3/umbrella"
UNISWAP_DOC = "https://developers.uniswap.org/docs/protocols/v3/guides"

MODULES = {
    "aave-v3": {"protocol": "Aave", "version": "3", "name": "Aave V3 lending", "documentation": LENDING_DOC},
    "aave-umbrella": {"protocol": "Aave", "version": "Umbrella", "name": "Aave Umbrella staking", "documentation": UMBRELLA_DOC},
    "uniswap-v3": {"protocol": "Uniswap", "version": "3", "name": "Uniswap V3", "documentation": UNISWAP_DOC},
}

# These are role-based candidates. Deployed code may be older than the ABI.
AAVE_INTERFACES = {
    "POOL": "IPool", "POOL_CONFIGURATOR": "IPoolConfigurator",
    "POOL_ADDRESSES_PROVIDER": "IPoolAddressesProvider", "ACL_MANAGER": "IACLManager",
    "ORACLE": "IAaveOracle", "DEFAULT_INCENTIVES_CONTROLLER": "IRewardsController",
    "WETH_GATEWAY": "IWrappedTokenGatewayV3", "UI_POOL_DATA_PROVIDER": "IUiPoolDataProvider",
    "STATA_FACTORY": "IStataTokenFactory", "UMBRELLA": "IUmbrella",
    "UMBRELLA_REWARDS_CONTROLLER": "IUmbrellaRewardsController",
}
UNISWAP_INTERFACES = {
    "UniswapV3Factory": "IUniswapV3Factory", "SwapRouter02": "SwapRouter02",
    "SwapRouter": "ISwapRouter", "QuoterV2": "IQuoterV2",
    "NonfungiblePositionManager": "INonfungiblePositionManager",
    "TickLens": "ITickLens", "V3Migrator": "IV3Migrator",
}

# interface, operation, methods, description, prerequisites
OPERATIONS = [
    ("IPool", "supply", ["supply", "supplyWithPermit", "deposit"], "Deposit a reserve asset and receive aTokens.", ["active unpaused reserve", "unfrozen supply", "balance and allowance or valid permit", "supply cap"]),
    ("IPool", "withdraw", ["withdraw"], "Redeem supplied assets by burning aTokens.", ["aToken balance", "reserve liquidity", "healthy remaining collateral", "reserve not paused"]),
    ("IPool", "borrow", ["borrow"], "Borrow a reserve asset against collateral or delegated credit.", ["borrowing enabled", "collateral and health factor", "borrow cap and reserve liquidity", "credit delegation when borrowing for another account", "supported rate mode"]),
    ("IPool", "repay", ["repay", "repayWithPermit", "repayWithATokens"], "Reduce outstanding debt with underlying assets or aTokens.", ["matching debt and rate mode", "balance and allowance or permit", "aToken repayment uses the caller's position"]),
    ("IPool", "set-collateral", ["setUserUseReserveAsCollateral"], "Enable or disable an asset as collateral.", ["supplied reserve balance", "collateral eligibility", "health factor after change"]),
    ("IPool", "set-emode", ["setUserEMode"], "Select an efficiency mode category for a lending position.", ["category exists", "debt and collateral compatible with category", "health factor after change"]),
    ("IPool", "flash-loan", ["flashLoan", "flashLoanSimple"], "Borrow liquidity through a receiver callback within one transaction.", ["receiver contract and callback", "available liquidity and enabled reserve", "repayment plus premium or permitted debt opening"]),
    ("IPool", "liquidate", ["liquidationCall"], "Repay eligible unhealthy debt in exchange for collateral.", ["position meets liquidation conditions", "eligible debt and collateral", "debt asset allowance and balance", "close factor and liquidation constraints"]),
    ("IPool", "position-manager", ["approvePositionManager", "renouncePositionManagerRole", "setUserEModeOnBehalfOf", "setUserUseReserveAsCollateralOnBehalfOf"], "Manage or use delegated position-management permissions.", ["deployment supports this interface revision", "required user authorization", "lending position constraints"]),
    ("IRewardsController", "claim-lending-rewards", ["claimRewards", "claimRewardsToSelf", "claimAllRewards", "claimAllRewardsToSelf"], "Claim accrued lending incentives.", ["eligible incentive assets", "accrued rewards", "valid recipient"]),
    ("IWrappedTokenGatewayV3", "native-token-lending", ["depositETH", "withdrawETH", "withdrawETHWithPermit", "borrowETH", "repayETH"], "Wrap or unwrap the native token when accessing Aave lending.", ["gateway and pool agree", "corresponding supply, withdrawal, borrowing or repayment conditions", "gateway allowances or credit delegation"]),
    ("IStataTokenV2", "wrap-atokens", ["deposit", "depositATokens", "depositWithPermit", "mint"], "Acquire static wrapper shares for interest-bearing assets.", ["correct underlying or aToken", "balance and allowance or permit", "wrapper not paused"]),
    ("IStataTokenV2", "unwrap-atokens", ["withdraw", "redeem", "redeemATokens"], "Redeem static wrapper shares.", ["share ownership or allowance", "withdrawal limits and reserve liquidity"]),
    ("IAToken", "transfer-atokens", ["transfer", "transferFrom"], "Transfer aToken ownership between addresses; this is not supply.", ["aToken balance", "allowance for transferFrom", "health factor validation"]),
    ("IUmbrellaStakeToken", "stake", ["deposit", "depositWithPermit", "mint"], "Deposit a supported Umbrella vault asset for slashable stake shares.", ["correct vault asset", "balance and allowance or permit", "vault not paused", "accept slashing exposure"]),
    ("IUmbrellaStakeToken", "start-cooldown", ["cooldown", "cooldownOnBehalfOf", "cooldownWithPermit"], "Start the cooldown needed to redeem stake shares.", ["stake shares", "owner or authorized operator/permit", "current vault cooldown settings"]),
    ("IUmbrellaStakeToken", "unstake", ["redeem", "withdraw"], "Redeem stake during the permitted withdrawal window.", ["cooldown completed", "within unstake window", "share ownership or allowance", "current exchange rate and withdrawal limits"]),
    ("IUmbrellaStakeToken", "set-cooldown-operator", ["setCooldownOperator"], "Authorize an operator to start cooldown.", ["share owner authorization"]),
    ("IUmbrellaRewardsController", "claim-staking-rewards", ["claimAllRewards", "claimAllRewardsPermit", "claimSelectedRewards", "claimSelectedRewardsPermit"], "Claim accrued Umbrella incentives.", ["eligible stake assets", "accrued rewards", "valid authorization for permit variants"]),
    ("ISwapRouter", "swap-exact-input", ["exactInputSingle", "exactInput"], "Swap a fixed input for at least a specified output.", ["token allowance and balance", "valid pool path", "minimum output", "deadline", "pool liquidity"]),
    ("ISwapRouter", "swap-exact-output", ["exactOutputSingle", "exactOutput"], "Buy a fixed output within a maximum input.", ["token allowance and balance", "valid reverse-encoded multihop path where applicable", "maximum input", "deadline", "pool liquidity"]),
    ("SwapRouter02", "swap-exact-input", ["exactInputSingle", "exactInput"], "Swap a fixed input using SwapRouter02.", ["token allowance and balance", "valid pool path", "minimum output", "pool liquidity", "use deadline-bearing multicall when required"]),
    ("SwapRouter02", "swap-exact-output", ["exactOutputSingle", "exactOutput"], "Buy a fixed output using SwapRouter02.", ["token allowance and balance", "maximum input", "valid path and pool liquidity", "use deadline-bearing multicall when required"]),
    ("IQuoterV2", "quote", ["quoteExactInputSingle", "quoteExactInput", "quoteExactOutputSingle", "quoteExactOutput"], "Simulate a swap quote using eth_call; ABI mutability is nonpayable.", ["valid path", "query at a known block", "quote is not a guarantee of execution price"]),
    ("IUniswapV3Factory", "create-pool", ["createPool"], "Create a V3 pool for a token pair and enabled fee tier.", ["distinct valid tokens", "enabled fee tier", "pool does not already exist"]),
    ("IUniswapV3Pool", "initialize-pool", ["initialize"], "Set a new pool's initial square-root price.", ["pool not initialized", "valid square-root price"]),
    ("IUniswapV3Pool", "pool-swap", ["swap"], "Swap directly against a pool using a payment callback.", ["valid price limit", "callback settlement", "pool liquidity"]),
    ("IUniswapV3Pool", "pool-flash", ["flash"], "Borrow pool tokens and repay principal plus fees in a callback.", ["callback receiver", "available balances", "repayment plus pool fees"]),
    ("IUniswapV3Pool", "pool-liquidity", ["mint", "burn", "collect"], "Manage tick-range liquidity directly at the pool.", ["valid ticks and spacing", "position ownership", "mint callback settlement", "burn and collect are separate steps"]),
    ("INonfungiblePositionManager", "create-position", ["mint"], "Create an NFT representing a concentrated-liquidity position.", ["initialized pool", "valid tick range", "token balances and allowances", "amount minima and deadline"]),
    ("INonfungiblePositionManager", "increase-liquidity", ["increaseLiquidity"], "Add liquidity to an existing NFT position.", ["existing position", "token balances and allowances", "amount minima and deadline"]),
    ("INonfungiblePositionManager", "decrease-liquidity", ["decreaseLiquidity"], "Remove liquidity, leaving owed tokens to be collected.", ["NFT owner or approved operator", "available position liquidity", "amount minima and deadline"]),
    ("INonfungiblePositionManager", "collect-fees", ["collect"], "Collect tokens owed to a position, including fees and removed liquidity.", ["NFT owner or approved operator", "valid recipient and collection limits"]),
    ("INonfungiblePositionManager", "close-position", ["burn"], "Burn an empty NFT position.", ["NFT owner or approved operator", "zero liquidity", "all owed tokens collected"]),
    ("INonfungiblePositionManager", "transfer-position", ["transferFrom", "safeTransferFrom"], "Transfer a position NFT to another address.", ["NFT owner or approved operator", "receiver compatibility for safe transfer"]),
    ("IV3Migrator", "migrate-v2-liquidity", ["migrate"], "Convert eligible V2 liquidity into a V3 position.", ["V2 LP balance and approval", "target pool and tick range", "amount minima and deadline"]),
]

ADAPTERS = {
    ("IPool", "supply(address,uint256,address,uint16)"),
    ("IPool", "withdraw(address,uint256,address)"),
    ("IPool", "borrow(address,uint256,uint256,uint16,address)"),
    ("IPool", "repay(address,uint256,uint256,address)"),
    ("SwapRouter02", "exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))"),
}

ADMIN_INTERFACES = {"IPoolConfigurator", "IPoolAddressesProvider", "IACLManager", "IAaveOracle"}
ADMIN_METHODS = {
    "IUniswapV3Factory": {"enableFeeAmount", "setOwner"},
    "IUniswapV3Pool": {"collectProtocol", "setFeeProtocol"},
    "IUmbrellaStakeToken": {"initialize", "pause", "unpause", "slash", "setCooldown", "setUnstakeWindow", "emergencyEtherTransfer", "emergencyTokenTransfer", "transferOwnership", "renounceOwnership"},
    "IPool": {"configureEModeCategory", "configureEModeCategoryBorrowableBitmap", "configureEModeCategoryCollateralBitmap", "configureEModeCategoryLtvzeroBitmap", "dropReserve", "initReserve", "rescueTokens", "resetIsolationModeTotalDebt", "setConfiguration", "setLiquidationGracePeriod", "updateFlashloanPremium"},
}


def module_for(interface: str) -> str:
    if interface.startswith("IUmbrella"):
        return "aave-umbrella"
    if interface in {"IUniswapV3Factory", "IUniswapV3Pool", "ISwapRouter", "SwapRouter02", "IQuoterV2", "INonfungiblePositionManager", "IV3Migrator", "ITickLens"}:
        return "uniswap-v3"
    return "aave-v3"


def permission(interface: str, entry: dict) -> str:
    if entry["stateMutability"] in {"view", "pure"}:
        return "read_only"
    name = entry["name"]
    if interface == "IQuoterV2":
        return "simulation_only"
    if interface in ADMIN_INTERFACES or name in ADMIN_METHODS.get(interface, set()):
        return "privileged_role_required"
    if name.endswith("Callback") or (interface == "IPool" and name == "finalizeTransfer"):
        return "callback_or_contract_only"
    if any(i == interface and name in methods for i, _, methods, _, _ in OPERATIONS):
        return "conditional_user_operation"
    # ABI mutability does not reveal authorization. Keep unknown methods explicit.
    return "unreviewed"
