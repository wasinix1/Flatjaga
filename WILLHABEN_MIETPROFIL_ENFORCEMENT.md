# Willhaben Mietprofil Enforcement Mode

## Overview

This feature implements a robust method to enforce that the "Mietprofil teilen" (Share Tenant Profile) checkbox is checked when contacting Willhaben listings. This addresses the known issue where React components don't load in time, causing the checkbox status to be incorrectly detected.

## The Problem

- Willhaben uses React components that take time to load and hydrate
- The "Mietprofil teilen" checkbox should be auto-checked for logged-in users
- Race conditions with React hydration often cause the checkbox to fail to be checked
- This results in contacts being sent without the tenant profile being shared

## The Solution

### Enforcement Modes: FAST vs STABLE

When enforcement is enabled, you choose between two modes:

**FAST Mode** (Default when enforcement enabled):
- Simple 2-method state verification
- Single attempt with 4 click strategies
- Quick and efficient
- Good for most use cases

**STABLE Mode** (Maximum reliability):
- 4-method state detection with confidence scoring
- Network idle detection (waits for page fully loaded)
- State persistence verification (checks state after 500ms)
- Viewport scrolling with smooth animation
- Randomized strategy order (stealth)
- 3 retry attempts with exponential backoff
- Variable human-like delays

## Configuration

Add these lines to your `config.yaml` under the Willhaben section:

```yaml
# Willhaben auto-contact configuration
willhaben_auto_contact: true
willhaben_headless: true
willhaben_delay_min: 0.5
willhaben_delay_max: 2.0

# Enforce Mietprofil sharing checkbox is checked (recommended if checkbox often fails)
willhaben_enforce_mietprofil_sharing: false  # Set to true to enable enforcement mode

# Enable stable mode for maximum reliability and stealth (requires enforcement enabled)
willhaben_mietprofil_stable_mode: false  # Set to true for enhanced features
```

### Configuration Modes

**Mode 1: Disabled (Default)**
```yaml
willhaben_enforce_mietprofil_sharing: false
willhaben_mietprofil_stable_mode: false
```
- No active checking, relies on Willhaben's auto-check
- Minimal interaction with the page

**Mode 2: FAST Enforcement**
```yaml
willhaben_enforce_mietprofil_sharing: true
willhaben_mietprofil_stable_mode: false
```
- Actively checks and enforces the checkbox
- 2-method state verification (is_selected + JS checked)
- Single attempt with 4 click strategies
- Quick and efficient
- Good for most use cases

**Mode 3: STABLE Enforcement (Recommended for A/B Testing)**
```yaml
willhaben_enforce_mietprofil_sharing: true
willhaben_mietprofil_stable_mode: true
```
- All FAST mode features PLUS:
- Network idle detection (waits for page fully loaded)
- Enhanced 4-method state detection with confidence scoring
- State persistence checking (verifies checkbox stays checked after 500ms)
- Viewport scrolling with smooth animation (ensures element visible)
- Randomized strategy order (less predictable pattern)
- Variable delays (more human-like timing)
- 3 retry attempts with exponential backoff (0.5s, 1s, 2s)
- Maximum reliability and stealth

### When to Enable Each Mode

**Enable FAST Mode** if:
- You frequently see listings contacted without the Mietprofil being shared
- You want good reliability without maximum overhead
- You're experiencing the React loading timing issue occasionally
- You want quick enforcement without extra verification

**Enable STABLE Mode** if:
- FAST mode still has occasional failures
- You want maximum reliability and detection resistance
- You're doing A/B testing between FAST and STABLE modes
- You value stealth and human-like behavior
- You need state persistence verification to protect against React re-renders
- You want comprehensive confidence-scored state detection

**Keep Disabled** (default) if:
- The auto-check mechanism is working reliably for you
- You want absolute minimum page interaction
- You've verified checkbox is consistently working

## Implementation Details

### Code Changes

1. **`flathunter/willhaben_contact_bot.py`**
   - Added `enforce_mietprofil_sharing` and `mietprofil_stable_mode` parameters to `__init__`
   - Added helper methods:
     - `_wait_for_network_idle()`: Detects when network requests complete
     - `_get_comprehensive_checkbox_state()`: 4-method state verification
     - `_verify_checkbox_state_persistence()`: Checks state doesn't change after 500ms
     - `_ensure_element_in_viewport()`: Smooth scrolling into view
   - Rewrote `_enforce_mietprofil_checkbox()` with stable mode logic
   - Updated email form handling to call enforcement when enabled

2. **`flathunter/willhaben_contact_processor.py`**
   - Added config reading for both enforcement and stable mode settings
   - Passes both settings to all bot instances

### Stable Mode Features Explained

**1. Network Idle Detection**
- Monitors `window.performance.getEntriesByType('resource')`
- Waits until no new network requests for 0.5 seconds
- Ensures page is fully loaded before interacting
- Timeout: 2 seconds max

**2. Enhanced State Detection (4 Methods)**
```python
is_selected()           # Selenium native check
js_checked              # JavaScript checked property
has_checked_class       # React wrapper CSS classes
svg_visible             # Checkmark icon visibility
```
- Uses majority vote (2/3 agreement = high confidence)
- Trusts `is_selected()` and `js_checked` over visual indicators

**3. State Persistence Verification**
- After clicking, waits 500ms
- Re-checks state with all 4 methods
- Protects against React re-renders unchecking the box
- Retries if state doesn't persist

**4. Viewport Scrolling**
- Checks if element is in viewport before clicking
- Smooth scroll if needed (`behavior: 'smooth'`)
- More human-like than instant scrolling
- Centers element in viewport

**5. Stealth Features**
- **Randomized strategy order**: Different click sequence each time
- **Variable delays**: 0.15-0.25s instead of fixed 0.2s
- **Label-first clicking**: Most human-like interaction
- **Smooth scrolling**: Natural animation instead of instant jump

**6. Retry Logic**
- 3 total attempts (vs 1 in FAST mode)
- Exponential backoff: 0.5s, 1s, 2s
- Each retry uses fresh randomized strategy order
- Comprehensive error logging

### Technical Approach (FAST Mode)

The FAST enforcement method uses this approach:

```python
# 1. Wait for checkbox and wrapper to be present and stable
for attempt in range(max_attempts):
    checkbox = find_element(By.ID, "shareTenantProfile")
    wrapper = find_element(By.CSS_SELECTOR, "div.Checkbox__StyledCheckbox-sc-7kkiwa-9")
    if both_exist:
        break
    sleep(0.2)

# 2. Additional delay for React event handlers to attach
sleep(0.3)

# 3. Check current state with multiple methods
is_checked = checkbox.is_selected()
js_checked = execute_script("return checkbox.checked")

# 4. If not checked, try multiple click strategies
strategies = [
    click_input_element,
    click_via_javascript,
    click_styled_wrapper,
    click_label
]

# 5. Verify after each click attempt
verify_checked_after_click()
```

## HTML Elements Targeted

The checkbox structure:

```html
<div class="Box-sc-wfmb7k-0 bkWefa">
  <label class="Checkbox__CheckboxLabel-sc-7kkiwa-7 hTyxpL">
    <input type="checkbox"
           id="shareTenantProfile"
           data-testid="share-tenant-profile-checkbox"
           name="shareTenantProfile">
    <div class="Checkbox__CheckboxInputWrapper-sc-7kkiwa-8 dVyplE">
      <div class="Checkbox__StyledCheckbox-sc-7kkiwa-9 flZUsv">
        <!-- SVG icons -->
      </div>
    </div>
    <span id="shareTenantProfile-label">Mietprofil teilen</span>
  </label>
</div>
```

## Logging

**Disabled Mode (Default):**
```
INFO: Mietprofil checkbox should be auto-checked (logged-in users)
```

**FAST Enforcement Mode:**
```
INFO: Enforcing Mietprofil checkbox [FAST mode]...
DEBUG: ✓ Checkbox stable (attempt 3)
DEBUG: Initial state: False
INFO: Mietprofil checkbox not checked - enforcing...
INFO: ✓ Checkbox enforced via click label
```

**STABLE Mode:**
```
INFO: Enforcing Mietprofil checkbox [STABLE mode]...
DEBUG: Waiting for network idle...
DEBUG: ✓ Network idle detected after 0.87s
DEBUG: ✓ Checkbox stable (attempt 2)
DEBUG: ✓ Mietprofil checkbox already in viewport
DEBUG: State check: is_selected=True, js_checked=True, svg_visible=True, confidence=high, final=True
DEBUG: Initial state: True (confidence: high)
DEBUG: ✓ State persistence verified: True
INFO: ✓ Mietprofil checkbox already checked (verified)
```

**STABLE Mode with Retry:**
```
INFO: Enforcing Mietprofil checkbox [STABLE mode]...
DEBUG: ✓ Checkbox stable (attempt 4)
DEBUG: Initial state: False (confidence: high)
INFO: Mietprofil checkbox not checked - enforcing...
DEBUG:   click styled wrapper clicked but not checked
DEBUG:   click via JavaScript failed: ...
INFO: ✓ Checkbox enforced via click label (verified)
```

## Testing

To test the enforcement mode:

1. Enable it in config.yaml
2. Run the bot with a visible browser (headless=false) to observe
3. Watch the logs to see which strategy succeeds
4. Verify the checkbox is checked before the form is submitted

## Future Improvements

Potential enhancements:

- Configurable wait timeout (currently hardcoded to 3 seconds)
- More sophisticated React hydration detection
- Fallback to Selenium WebDriverWait with explicit conditions
- Integration with retry logic if enforcement fails
