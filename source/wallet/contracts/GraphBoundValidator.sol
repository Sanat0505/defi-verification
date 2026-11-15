// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @dev ABI-compatible with Kernel v0.3.1 / ERC-7579 IValidator (EntryPoint 0.7).
struct PackedUserOperation {
    address sender;
    uint256 nonce;
    bytes initCode;
    bytes callData;
    bytes32 accountGasLimits;
    uint256 preVerificationGas;
    bytes32 gasFees;
    bytes paymasterAndData;
    bytes signature;
}

/// @notice Owner-installed, graph-authority-attested, one-operation validator.
/// No direct caller hook, ERC-1271 authority, enable signature or sudo fallback.
contract GraphBoundValidator {
    uint256 public constant CHAIN_ID = 11155111;
    bytes32 public constant DOMAIN = keccak256("DeFiGraphAuthorization:v1");
    bytes4 public constant EXECUTE = bytes4(keccak256("execute(bytes32,bytes)"));
    uint256 private constant HALF_N =
        0x7fffffffffffffffffffffffffffffff5d576e7357a4501ddfe92f46681b20a0;

    struct Config {
        address authority;
        address executor;
        uint256 epoch;
        uint256 maxGasCost;
    }
    struct Permit {
        bytes32 approvalId;
        uint48 validAfter;
        uint48 validUntil;
        bytes authoritySignature;
        bytes executorSignature;
    }
    mapping(address => Config) public configs;
    // Never clear consumed approval IDs on uninstall/reinstall.
    mapping(address => mapping(bytes32 => bool)) public used;

    event Installed(address indexed account, address authority, address executor, uint256 epoch);
    event Consumed(address indexed account, bytes32 indexed approvalId, bytes32 callDataHash);

    function onInstall(bytes calldata data) external payable {
        Config storage c = configs[msg.sender];
        require(c.authority == address(0), "already installed");
        (address authority, address executor, uint256 maxGasCost) =
            abi.decode(data, (address, address, uint256));
        require(authority != address(0) && executor != address(0) && authority != executor, "roles");
        require(maxGasCost > 0, "gas budget");
        c.authority = authority;
        c.executor = executor;
        c.maxGasCost = maxGasCost;
        c.epoch++;
        emit Installed(msg.sender, authority, executor, c.epoch);
    }

    function onUninstall(bytes calldata) external payable {
        Config storage c = configs[msg.sender];
        require(c.authority != address(0), "not installed");
        c.authority = address(0);
        c.executor = address(0);
        c.maxGasCost = 0;
    }

    function isModuleType(uint256 id) external pure returns (bool) { return id == 1; }
    function isInitialized(address account) external view returns (bool) {
        return configs[account].authority != address(0);
    }
    function isValidSignatureWithSender(address, bytes32, bytes calldata) external pure returns (bytes4) {
        return 0xffffffff;
    }

    function authorizationHash(address account, bytes32 approvalId, bytes32 callDataHash,
        uint48 validAfter, uint48 validUntil) public view returns (bytes32)
    {
        Config memory c = configs[account];
        return keccak256(abi.encode(DOMAIN, block.chainid, address(this), account,
            c.executor, c.epoch, approvalId, callDataHash, validAfter, validUntil));
    }

    function validateUserOp(PackedUserOperation calldata op, bytes32 opHash)
        external payable returns (uint256)
    {
        Config memory c = configs[msg.sender];
        if (block.chainid != CHAIN_ID || op.sender != msg.sender || c.authority == address(0)) return 1;
        if (op.initCode.length != 0 || op.callData.length < 4 || bytes4(op.callData[:4]) != EXECUTE) return 1;
        Permit memory p = abi.decode(op.signature, (Permit));
        if (p.approvalId == bytes32(0) || used[msg.sender][p.approvalId]) return 1;
        if (p.validUntil <= p.validAfter || p.validUntil - p.validAfter > 125) return 1;
        // EntryPoint enforces the returned time bounds. Avoid TIMESTAMP here:
        // ERC-4337 validation opcode rules forbid time-dependent validation.
        uint256 gas = uint128(uint256(op.accountGasLimits)) + uint256(uint128(bytes16(op.accountGasLimits)))
            + op.preVerificationGas;
        if (op.paymasterAndData.length != 0) {
            if (op.paymasterAndData.length < 52) return 1;
            gas += uint128(bytes16(op.paymasterAndData[20:36]));
            gas += uint128(bytes16(op.paymasterAndData[36:52]));
        }
        uint256 fee = uint128(uint256(op.gasFees));
        if (fee == 0 || gas > c.maxGasCost / fee) return 1;
        bytes32 callHash = keccak256(op.callData);
        if (_recover(authorizationHash(msg.sender, p.approvalId, callHash, p.validAfter, p.validUntil),
            p.authoritySignature) != c.authority) return 1;
        if (_recover(opHash, p.executorSignature) != c.executor) return 1;
        used[msg.sender][p.approvalId] = true;
        emit Consumed(msg.sender, p.approvalId, callHash);
        return (uint256(p.validUntil) << 160) | (uint256(p.validAfter) << 208);
    }

    function _recover(bytes32 digest, bytes memory signature) private pure returns (address) {
        if (signature.length != 65) return address(0);
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := mload(add(signature, 32))
            s := mload(add(signature, 64))
            v := byte(0, mload(add(signature, 96)))
        }
        if (uint256(s) > HALF_N || (v != 27 && v != 28)) return address(0);
        return ecrecover(keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", digest)), v, r, s);
    }
}
