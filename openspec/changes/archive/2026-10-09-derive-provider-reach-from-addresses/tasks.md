## 1. One connection, two addresses

- [x] 1.1 `anthropic_base_url` on the config, create, patch and read; proxy, secret destination and stored-key gate use it; tests
- [x] 1.2 Add and Edit ask for the two addresses; the protocol follows; the switch test uses the Anthropic address; tests
- [x] 1.3 ADR one-connection-serves-both-wires

## 2. Reach follows the addresses

- [x] 2.1 `served_agents`; reach ignores scope; kind drops scope; activate refuses an agent the addresses do not serve; tests
- [x] 2.2 Startup: retire the off switch and scope, fill Anthropic addresses; tests
- [x] 2.3 Detail header says which agents can use it; no scope control or switch; tests
- [x] 2.4 ADR provider-reach-is-what-its-addresses-serve

## 3. Vendors

- [x] 3.1 Sixteen more presets with documented addresses, a region choice, marks; tests

## 4. Docs and canvas

- [x] 4.1 Providers guide (en/zh); ADR index rows
- [x] 4.2 Agents canvas Providers boards
