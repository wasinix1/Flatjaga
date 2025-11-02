# Willhaben Mietprofil Enforcement Mode

## Overview

This feature implements a robust method to enforce that the "Mietprofil teilen" (Share Tenant Profile) checkbox is checked when contacting Willhaben listings. This addresses the known issue where React components don't load in time, causing the checkbox status to be incorrectly detected.

## The Problem

- Willhaben uses React components that take time to load and hydrate
- The "Mietprofil teilen" checkbox should be auto-checked for logged-in users
- Race conditions with React hydration often cause the checkbox to fail to be checked
- This results in contacts being sent without the tenant profile being shared

## The Solution

### Enforcement Mode

When enabled, the bot will:

1. **Wait for React to fully load** (up to 3 seconds)
   - Checks for both the checkbox input element and the React wrapper component
   - Verifies the component has stabilized before interacting
   - Uses multiple indicators to ensure React hydration is complete

2. **Verify checkbox state**
   - Checks using both `is_selected()` and JavaScript `checked` property
   - Only takes action if the checkbox is not checked

3. **Enforce checkbox is checked**
   - Tries multiple strategies to check the checkbox:
     - Direct click on input element
     - JavaScript click
     - Click on the styled wrapper div
     - Click on the label element
   - Verifies after each attempt that the checkbox was successfully checked

4. **Comprehensive logging**
   - Logs each step of the process
   - Reports which strategy succeeded
   - Warns if all strategies fail

## Configuration

Add this line to your `config.yaml` under the Willhaben section:

```yaml
# Willhaben auto-contact configuration
willhaben_auto_contact: true
willhaben_headless: true
willhaben_delay_min: 0.5
willhaben_delay_max: 2.0

# Enforce Mietprofil sharing checkbox is checked (recommended if checkbox often fails)
willhaben_enforce_mietprofil_sharing: false  # Set to true to enable enforcement mode
```

### When to Enable

Enable this mode (`willhaben_enforce_mietprofil_sharing: true`) if:

- You frequently see listings contacted without the Mietprofil being shared
- You want to ensure 100% reliability for the checkbox
- You're experiencing the React loading timing issue

Keep it disabled (default) if:

- The auto-check mechanism is working reliably for you
- You want to minimize interaction with the page to avoid detection

## Implementation Details

### Code Changes

1. **`flathunter/willhaben_contact_bot.py`**
   - Added `enforce_mietprofil_sharing` parameter to `__init__`
   - Added `_enforce_mietprofil_checkbox()` method with robust waiting logic
   - Updated email form handling to call enforcement method when enabled

2. **`flathunter/willhaben_contact_processor.py`**
   - Added config reading for `willhaben_enforce_mietprofil_sharing`
   - Passes the setting to all bot instances

### Technical Approach

The enforcement method uses a multi-layered approach:

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

When enforcement mode is enabled, you'll see logs like:

```
INFO: Enforcing Mietprofil checkbox (waiting for React to load)...
DEBUG: ✓ Checkbox found and stable (attempt 3)
DEBUG: Checkbox state: is_selected()=False, JS checked=False
INFO: Mietprofil checkbox not checked - enforcing...
INFO: ✓ Mietprofil checkbox checked successfully using click via JavaScript
```

If disabled (default):

```
INFO: Mietprofil checkbox should be auto-checked (logged-in users)
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
