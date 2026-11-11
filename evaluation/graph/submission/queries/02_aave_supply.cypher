// Read-only structural example: Aave V3 USDC supply on Ethereum Sepolia.
// Returns actual connected paths; does not create presentation metadata.
// Freshness, intent validation and wallet readiness are separate checks.
MATCH network=(chain:Chain {chain_id:11155111})-[:HOSTS]->
  (deployment:ProtocolDeployment {key:'aave-v3:11155111', verified:true})
MATCH protocol=(family:ProtocolFamily)-[:HAS_DEPLOYMENT]->(deployment)
MATCH supported=(deployment)-[:SUPPORTS_ACTION]->(action:Action {name:'supply'})
MATCH execution=(deployment)-[:DEPLOYED_CONTRACT {role:'pool', active:true}]->
  (contract:Contract {verified:true})-[:EXPOSES_FUNCTION]->
  (fn:Function {verified:true, purpose:'execute'})-[:IMPLEMENTS_ACTION]->(action)
MATCH asset=(deployment)-[:HAS_RESERVE {active:true}]->
  (reserve:Reserve {active:true, verified:true})-[:UNDERLYING_ASSET]->
  (token:Token {symbol:'USDC', chain_id:11155111, verified:true})
MATCH reserve_action=(reserve)-[:SUPPORTS_ACTION]->(action)
RETURN network, protocol, supported, execution, asset, reserve_action;
