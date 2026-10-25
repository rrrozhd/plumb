# Mastercard AP4M integration

This demo uses XRPL EVM testnet and requires an onboarded team. Follow the
[sponsor instructions](https://hackathon.ap4m.build/sdk/AGENTS.md).
Use Node.js 22.13 or later. From this directory:

```sh
npm ci
curl --fail --location https://hackathon.ap4m.build/sdk/ap4m-hackathon-sdk.js -o ap4m-hackathon-sdk.cjs
curl --fail --location https://hackathon.ap4m.build/sdk/ap4m-x402.mjs -o ap4m-x402.mjs
```

The sponsor helpers are downloaded locally and ignored by Git. Their original
hackathon restrictions apply. The npm SDK comes from the sponsor service via
`package.json` and the lockfile.

Create the ignored `../env/ap4m.env` with your team's settings:

```dotenv
AP4M_API_URL=https://hackathon.ap4m.build
AGENT_SIGNING_KEY=
MERCHANT_SUBMITTER_KEY=
MERCHANT_ID=
MERCHANT_PAYOUT_ADDRESS=
```

Set `AP4M.team` in `env.mjs` to your registered team name (the demo default is
`Plumb`). `AGENT_SIGNING_KEY` must correspond to that team's onboarded agent. The existing buyer
also supports `FUNDING_PRIVATE_KEY` when that is the registered agent wallet.
Do not publish private keys. Team onboarding and funding happen in the sponsor
portal; the code sends signatures, never keys, to the service.

From the repository root, start the Python API and merchant in separate terminals:

```sh
uv run python -m plumb.api
```

```sh
cd ap4m
node merchant.mjs
```

Then run the buyer in another terminal:

```sh
cd ap4m
node agent.mjs
```

The buyer reuses an existing channel by default. `PLUMB_NEW_CHANNEL=1` requests
a fresh channel; the sponsor limits channels per budget deposit. Existing spend
caps remain in force. This integration is testnet-only.

`proof.py` assembles a completed local run into the recorded public demonstration
at `../site/public/ap4m-proof.json`. Its source databases and raw trails are local
artifacts and are not distributed. It reads the existing public receipt; it does
not make a new purchase.
