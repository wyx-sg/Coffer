## 1. Backend

- [x] 1.1 Move `sync` and `models` from `EXPERIMENTAL_FEATURES` to `GRADUATED_FEATURES` (no settings moved)
- [x] 1.2 Delete every gate that named them: the sync worker's and the attention source's, the provider projection's (and its `feature_off` decision), the model proxy's, usage ingest's, the price-list refresh's and the models-switch follower
- [x] 1.3 Update the backend tests: drop the sync/models off cases, cover graduation at startup and an ignored pin

## 2. Web UI

- [x] 2.1 `FeatureKey` is `knowledge | memory`; remove the `sync`/`models` tags from navigation, Overview, the palette and the agent Model surfaces
- [x] 2.2 Drop the Experimental label from Model providers and Sync; Settings → Features lists two features
- [x] 2.3 Update the frontend tests and fixtures

## 3. Docs and design

- [x] 3.1 Experimental-features guide (zh/en) names two features and says sync and models graduated
- [x] 3.2 Every zh/en page that says sync or model providers must be switched on first describes them as always on
- [x] 3.3 Design canvases: Settings → Features and the sidebar labels
