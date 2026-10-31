# Phase 0: Problems Encountered & Resolutions

### 1. PowerShell Runner Path Resolution on Windows
- **Problem:** The tool execution environment attempted to resolve `powershell` directly from the local directory or had a missing environment PATH pointer, resulting in `exec: powershell: executable file not found in %PATH%`.
- **Resolution:** Created a root shim `powershell.cmd` routing directly to `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe %*`. All subsequent PowerShell commands executed seamlessly.

### 2. Hatchling Editable Wheel Package Discovery
- **Problem:** When installing dependencies with `uv pip install -e ".[dev]"`, Hatchling failed with `ValueError: Unable to determine which files to ship inside the wheel... no directory that matches the name of your project (paytm_saathi_backend)`.
- **Resolution:** Added explicit wheel package mapping in `backend/pyproject.toml`:
  ```toml
  [tool.hatch.build.targets.wheel]
  packages = ["app"]
  ```

### 3. pnpm Dependency Build Script Approval (esbuild)
- **Problem:** In pnpm v12+, native binary build scripts are blocked by default with `ERR_PNPM_IGNORED_BUILDS` for safety when installing `esbuild`.
- **Resolution:** Executed `pnpm approve-builds --all` to authorize required development build binaries, enabling Vite and esbuild to install cleanly.

### 4. Rollup ESM vs. CommonJS Named Export Resolution in Monorepo
- **Problem:** `apps/employee-web` (Vite / Rollup) failed during production build with `error: "StatusChip" is not exported by "../../packages/design-tokens/dist/index.js"`. This occurred because `design-tokens` was compiling to CommonJS, and Rollup's static ESM analysis could not reliably infer named exports from wildcard re-exports.
- **Resolution:** Configured `packages/design-tokens` as a modern ESM package with `"type": "module"`, `"module": "ESNext"`, `"moduleResolution": "bundler"`, and explicit `package.json` export maps (`"exports": { ".": { "types": "./dist/index.d.ts", "import": "./dist/index.js", "default": "./dist/index.js" } }`). Rebuilt the package with `tsc`, enabling Vite to build with zero errors.
