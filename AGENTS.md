# Guidelines for AI Coding Agents & Teammates

This project is co-developed by multiple parallel workstreams. To prevent merge conflicts and regressions, all AI assistants and developers MUST adhere strictly to these rules:

---

## 1. Ownership & Boundary Constraints
- **Work within your workstream**: ONLY modify or create files assigned to your workstream in [docs/OWNERS.md](file:///d:/Year3%20semester2/PP/Flask/docs/OWNERS.md).
- **Protected Core Files (DO NOT TOUCH)**:
  - ❌ `models/*` (All tables are defined in Phase 0; contact the Team Lead for schema changes).
  - ❌ `migrations/*` (Never modify or run `flask db migrate`).
  - ❌ `app.py`, `config.py`, `extensions.py`.
  - ❌ `requirements.txt` (Pinned by Team Lead; do not add dependencies without approval).
  - ❌ Base layout templates (`templates/admin/master.html`, header/footer shares).

## 2. Business Logic & Service Layer
- **Keep routes thin**: Blueprints in `front/` and `admin/` must only parse request inputs, call domain services, and render responses.
- **Implement logic in `services/`**:
  - `services/stock_service.py` (Workstream A)
  - `services/order_service.py` (Workstream C)
  - `services/coupon_service.py` (Workstream D)
  - `services/report_service.py` (Workstream D)

## 3. Mandatory Standards
- **Monetary values**: Always use integer cents named `*_cents`. Use `helpers.money.to_cents()`, `from_cents()`, and `format_money()`.
- **Timestamps**: Always store naive UTC timestamps using `helpers.time.utc_now()`. Localize for display using `helpers.time.to_local(dt)`.
- **Telegram notifications**: Always use `helpers.telegram.send_telegram()` (or wrapper stubs). It executes asynchronously in a background thread and never raises into request handlers.
- **Security & Forms**: All state-changing operations MUST use `POST` and include the CSRF token:
  ```html
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
  ```
- **Concurrency**: Decrement stock using atomic SQL updates with rowcount verification. Do not use pessimistic locking.

## 4. Git & Verification Workflow
1. Branch from `develop` using `feature/<workstream-feature-name>`.
2. Run test suite before pushing:
   ```powershell
   pytest
   ```
3. Rebase against `develop` before opening a Pull Request.
