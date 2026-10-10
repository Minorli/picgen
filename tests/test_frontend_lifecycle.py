from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
APP_JS = ROOT_DIR / "static" / "app.js"


def run_frontend(function_names: list[str], script: str) -> None:
    source = APP_JS.read_text(encoding="utf-8")
    functions = []
    for name in function_names:
        start = re.search(rf"^(?:async )?function {name}\(", source, re.MULTILINE)
        assert start is not None
        end = re.search(r"^(?:async )?function |^init\(\)", source[start.end():], re.MULTILINE)
        assert end is not None
        functions.append(source[start.start():start.end() + end.start()])
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", "\n".join(functions) + "\n" + script],
        cwd=ROOT_DIR, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("old_response", ["success", "http_error", "network_error"])
def test_task_refresh_ignores_older_responses(old_response: str) -> None:
    run_frontend(["refreshGenerationJobs", "renderGenerationJobsPagination"], """
import assert from 'node:assert/strict';
const state = {currentUser: {id: 1}, generationJobs: []};
const refs = {jobCenterList: {innerHTML: ''}, jobCenterEmpty: {classList: {add() {}}}};
const requests = [];
function fetchJSON() { return new Promise((resolve, reject) => requests.push({resolve, reject})); }
function renderGenerationJobs(jobs) { state.generationJobs = jobs; refs.jobCenterList.innerHTML = jobs[0].status; }
const old = refreshGenerationJobs();
const latest = refreshGenerationJobs();
requests[1].resolve({response: {ok: true}, data: {jobs: [{id: 1, status: 'succeeded'}]}});
await latest;
""" + {
        "success": "requests[0].resolve({response: {ok: true}, data: {jobs: [{id: 1, status: 'started'}]}});",
        "http_error": "requests[0].resolve({response: {ok: false}, data: {}});",
        "network_error": "requests[0].reject(new Error('network disconnected'));",
    }[old_response] + """
await old;
assert.equal(state.generationJobs[0].status, 'succeeded');
assert.equal(refs.jobCenterList.innerHTML, 'succeeded');
""")


BOOTSTRAP_STAGES = [
    "loadUserPreferences", "refreshOrgUnits", "loadPromptRecipes", "refreshImageStats",
    "restoreWorkspaceState", "refreshTeamChatUnread", "refreshUsageSummary", "refreshGenerationJobs",
]


@pytest.mark.parametrize("interrupted_stage", [None, *BOOTSTRAP_STAGES])
def test_bootstrap_cannot_resume_after_user_context_changes(interrupted_stage: str | None) -> None:
    run_frontend(["startAuthenticatedApp", "userContextIsCurrent"], """
import assert from 'node:assert/strict';
const interruptedStage = """ + json.dumps(interrupted_stage) + """;
const state = {userContextEpoch: 1, currentUser: {id: 1}, appReady: false, persistenceReady: false};
const calls = [];
const noopNames = [
  'resetWorkspaceForUserScope', 'renderSimpleGalleryItems', 'loadTeamChatRecentDms', 'renderHistory',
  'loadSettings', 'updateLogoControlUI', 'updatePromptCounters', 'updatePromptModeUI',
  'updateGenerateIntentUI', 'updateEditSourceUI', 'updateEditMaskUI', 'updateOpenAIOptionUI',
  'updatePreviewAvailability', 'setMode', 'initializeUiMode', 'updateWorkflowStatus',
  'startTeamChatPolling', 'scheduleWorkspacePersist',
];
for (const name of noopNames) globalThis[name] = () => calls.push(name);
globalThis.historyStorageKey = () => 'history';
globalThis.loadJSON = () => [];
for (const name of """ + json.dumps(BOOTSTRAP_STAGES) + """) {
  globalThis[name] = async () => {
    calls.push(name);
    if (name === interruptedStage) {
      state.userContextEpoch += 1;
      state.currentUser = null;
      state.appReady = false;
      state.persistenceReady = false;
    }
    return false;
  };
}
const ready = await startAuthenticatedApp();
if (interruptedStage) {
  assert.equal(ready, false);
  assert.equal(state.appReady, false);
  assert.equal(state.persistenceReady, false);
  assert.equal(calls.at(-1), interruptedStage, 'stale startup continued modifying the workspace');
} else {
  assert.equal(ready, true);
  assert.equal(state.appReady, true);
  assert.equal(state.lastReadyUserId, 1);
}
""")


@pytest.mark.parametrize("ready", [True, False])
def test_login_enters_workspace_only_after_current_startup_completes(ready: bool) -> None:
    run_frontend(["submitAuthForm"], """
import assert from 'node:assert/strict';
const state = {authMode: 'login'};
const refs = {authUsernameInput: {value: 'test'}, authPasswordInput: {value: 'password'},
  authError: {textContent: ''}, loginAuthButton: {}, registerAuthButton: {}};
let entered = false;
function validateAuthFormInputs() { return true; }
async function fetchJSON() { return {response: {ok: true}, data: {user: {id: 1}}}; }
function setCurrentUser() {}
async function startAuthenticatedApp() { return """ + json.dumps(ready) + """; }
function enterAppShell() { entered = true; }
await submitAuthForm({preventDefault() {}});
assert.equal(entered, """ + json.dumps(ready) + """);
assert.equal(refs.loginAuthButton.disabled, false);
assert.equal(refs.registerAuthButton.disabled, false);
""")


def test_opening_external_result_cannot_replay_another_images_request() -> None:
    run_frontend(["resetReviewStateForExternalResult", "rerunLastGeneration"], """
import assert from 'node:assert/strict';
const state = {lastRegenerationRequest: {kind: 'generate', snapshot: {prompt: 'old image'}}};
let generated = false;
let error = '';
for (const name of ['setResultCountNotice', 'setResultSizeWarning', 'setRiskPanel', 'setTextFidelityPanel']) {
  globalThis[name] = () => {};
}
function setError(message) { error = message; }
function currentFormSnapshot() { return {}; }
function applyFormSnapshot() {}
async function submitGenerate() { generated = true; }
function userContextIsCurrent() { return true; }
function mergeRerunDraftSnapshots() { return {}; }
const window = {clearTimeout() {}};
resetReviewStateForExternalResult();
await rerunLastGeneration();
assert.equal(generated, false, 'historical result must not rerun a different image request');
assert.equal(error, '当前没有可复用的生成参数。');
""")


@pytest.mark.parametrize("submit", ["submitGenerate", "submitVariantGenerate", "submitEdit"])
def test_failed_generation_refreshes_task_history(submit: str) -> None:
    run_frontend([submit, "userContextIsCurrent"], """
import assert from 'node:assert/strict';
const state = {userContextEpoch: 1, lastResultImage: {name: 'input'}, editImage: {name: 'input'}};
const refs = {generatePromptInput: {value: 'test'}, editPromptInput: {value: 'test'}};
let refreshCount = 0;
let errors = [];
for (const name of ['resetDebugLog', 'appendDebugLine', 'updatePromptCounters',
  'updateEffectivePromptPreview', 'saveSettings', 'closePreview', 'previewPendingResult',
  'ensureRequestNotCancelled', 'ensureUserContextCurrent', 'setProgressPhase']) {
  globalThis[name] = () => {};
}
function setBusy(busy) { state.isBusy = busy; }
function setError(error) { errors.push(error); }
async function refreshGenerationJobs() { refreshCount++; }
function buildEffectiveGeneratePrompt() {
  return {originalPrompt: 'test', effectivePrompt: 'test', promptMode: 'free'};
}
function getSettings() { return {}; }
function generateReferenceImages() { return []; }
function hasStyleTransferReferences() { return false; }
function shouldUseCompanyLogo() { return false; }
function getExplicitItineraryId() { return ''; }
function rejectLegacyProgramLayoutBackgroundPrompt() { return false; }
function getGenerateSize() { return '1024x1024'; }
function getOpenAIImageOptions() { return {}; }
function getGenerateSampleCount() { return 1; }
async function confirmPromptBeforeRun() { return 'test'; }
function buildVisibleTextContract() { return {}; }
function withLogoLayoutPrompt(prompt) { return prompt; }
function withEditPreservePrompt(prompt) { return prompt; }
function currentFormSnapshot() { return {}; }
function cloneImageAsset(asset) { return asset; }
function modelInputAssetForLogoWorkflow(asset) { return asset; }
async function ensureAssetDataUrl() { return 'data:image/png;base64,eA=='; }
function inferMimeFromDataUrl() { return 'image/png'; }
function sourceImageIdentityFields() { return {}; }
function imageJobAdvancedOptions() { return {}; }
async function postJSON() { throw new Error('upstream failed'); }
await """ + submit + """();
assert.equal(errors.at(-1), 'upstream failed');
assert.equal(state.isBusy, false);
assert.equal(refreshCount, 1, 'failed task should appear without a manual refresh');
""")


@pytest.mark.parametrize("scenario", ["append", "retry", "refresh_race", "account_switch"])
def test_task_pagination_preserves_history_and_ignores_stale_pages(scenario: str) -> None:
    run_frontend(["refreshGenerationJobs", "renderGenerationJobsPagination"], """
import assert from 'node:assert/strict';
const state = {currentUser: {id: 1}, userContextEpoch: 1, generationJobs: []};
const button = {disabled: false, textContent: '', classList: {toggle(name, hidden) { button.hidden = hidden; }}};
const refs = {loadMoreJobsButton: button, jobCenterList: {innerHTML: ''},
  jobCenterEmpty: {classList: {add() {}}}};
const requests = [];
function fetchJSON(url) { return new Promise((resolve, reject) => requests.push({url, resolve, reject})); }
function renderGenerationJobs(jobs) { state.generationJobs = jobs; }
function page(index, ids, next) {
  requests[index].resolve({response: {ok: true}, data: {
    jobs: ids.map(id => ({id})), next_before_id: next,
  }});
}
const first = refreshGenerationJobs();
page(0, [30, 29], 29);
await first;
assert.equal(button.hidden, false);
assert.equal(button.disabled, false);
const older = refreshGenerationJobs({append: true});
assert.equal(requests[1].url, '/api/jobs?limit=20&before_id=29');
assert.equal(button.disabled, true);
await refreshGenerationJobs({append: true});
assert.equal(requests.length, 2, 'double click must not request the same page twice');
""" + {
        "append": """
page(1, [29, 28, 27], null);
await older;
assert.deepEqual(state.generationJobs.map(job => job.id), [30, 29, 28, 27]);
assert.equal(button.hidden, true);
await refreshGenerationJobs({append: true});
assert.equal(requests.length, 2);
""",
        "retry": """
requests[1].reject(new Error('network disconnected'));
await older;
assert.deepEqual(state.generationJobs.map(job => job.id), [30, 29]);
assert.equal(refs.jobCenterList.innerHTML, '');
assert.equal(button.disabled, false);
assert.match(button.textContent, /重试/);
const retry = refreshGenerationJobs({append: true});
assert.equal(requests[2].url, requests[1].url);
page(2, [28], null);
await retry;
assert.deepEqual(state.generationJobs.map(job => job.id), [30, 29, 28]);
""",
        "refresh_race": """
const refreshed = refreshGenerationJobs();
assert.equal(requests[2].url, '/api/jobs?limit=20');
page(2, [31, 30], 30);
await refreshed;
page(1, [28], null);
await older;
assert.deepEqual(state.generationJobs.map(job => job.id), [31, 30]);
assert.equal(state.generationJobsNextBeforeId, 30);
assert.equal(button.hidden, false);
assert.equal(button.disabled, false);
""",
        "account_switch": """
state.userContextEpoch++;
state.currentUser = {id: 2};
state.generationJobs = [];
state.generationJobsNextBeforeId = null;
state.generationJobsLoading = false;
renderGenerationJobsPagination();
page(1, [28], null);
await older;
assert.deepEqual(state.generationJobs, []);
assert.equal(button.hidden, true);
""",
    }[scenario])


def test_task_history_displays_all_loaded_jobs() -> None:
    run_frontend(["renderGenerationJobs", "jobStatusLabel"], """
import assert from 'node:assert/strict';
const state = {currentUser: {id: 1}};
const rendered = [];
const refs = {
  jobCenterList: {replaceChildren() { rendered.length = 0; }, append(item) { rendered.push(item); }},
  jobCenterEmpty: {classList: {toggle() {}}},
};
const document = {createElement() { return {append() {}, addEventListener() {}}; }};
function updateSimpleTimingEstimate() {}
function formatTimestamp() { return 'today'; }
const jobs = Array.from({length: 40}, (_, i) => ({id: 40 - i, status: 'succeeded'}));
renderGenerationJobs(jobs);
assert.equal(rendered.length, 40);
""")


def test_account_workspace_reset_clears_visible_tasks_before_new_history_loads() -> None:
    run_frontend([
        "resetWorkspaceForUserScope", "refreshGenerationJobs", "renderGenerationJobsPagination",
    ], """
import assert from 'node:assert/strict';
const state = {currentUser: {id: 1}, userContextEpoch: 1,
  generationJobs: [{id: 30, prompt: 'previous user private prompt'}],
  generationJobsNextBeforeId: 30, generationJobsRequestSeq: 1,
  generatedImageDetailRequestSeq: 1};
const button = {classList: {toggle(name, hidden) { button.hidden = hidden; }}};
const refs = {loadMoreJobsButton: button, jobCenterList: {innerHTML: 'previous user private prompt'},
  jobCenterEmpty: {classList: {add() {}}}, promptModeInputs: []};
const window = {clearTimeout() {}};
for (const name of ['cancelPendingPromptConfirmation', 'renderGalleryItems', 'renderSharedResults',
  'restoreSimpleDraft', 'setBusy', 'clearResult', 'clearGenerateForm', 'clearEditForm',
  'resetItineraryMapExample', 'clearSourcePreview', 'setError']) {
  globalThis[name] = () => {};
}
function renderGenerationJobs(jobs) {
  state.generationJobs = jobs;
  refs.jobCenterList.innerHTML = jobs.map(job => job.prompt).join('');
}
let resolveRequest;
function fetchJSON() { return new Promise(resolve => { resolveRequest = resolve; }); }
const previousRequest = refreshGenerationJobs({append: true});
const previousSequence = state.generationJobsRequestSeq;
state.currentUser = {id: 2};
state.userContextEpoch++;
resetWorkspaceForUserScope();
assert.deepEqual(state.generationJobs, []);
assert.equal(refs.jobCenterList.innerHTML, '');
assert.equal(state.generationJobsNextBeforeId, null);
assert.equal(state.generationJobsLoading, false);
assert.equal(button.hidden, true);
assert.ok(state.generationJobsRequestSeq > previousSequence);
resolveRequest({response: {ok: true}, data: {jobs: [{id: 29, prompt: 'private'}], next_before_id: 29}});
await previousRequest;
assert.deepEqual(state.generationJobs, []);
assert.equal(refs.jobCenterList.innerHTML, '');
assert.equal(button.hidden, true);
""")
