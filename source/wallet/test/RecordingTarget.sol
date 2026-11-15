// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// Test destination only: records dispatch, does not model DeFi economics.
contract RecordingTarget {
    event Called(address indexed caller, bytes data, uint256 value);
    fallback() external payable {
        emit Called(msg.sender, msg.data, msg.value);
        assembly { mstore(0, 1) return(0, 32) }
    }
}
