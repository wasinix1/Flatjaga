# Willhaben Mietprofil (Tenant Profile) Handling

## Overview

The bot automatically ensures the "Mietprofil teilen" (Share Tenant Profile) checkbox is checked when contacting Willhaben listings. This happens automatically with no configuration required.

## How It Works

### Verification at Submission Time

The bot verifies the Mietprofil checkbox **right before clicking the Submit button**:

1. **Check state** - Use JavaScript to check `checked` property (source of truth)
2. **Only click if unchecked** - If checkbox is NOT checked, click the label to check it
3. **Skip if checked** - If already checked, do nothing (clicking would uncheck it!)
4. **Skip if uncertain** - If state can't be determined, assume it's checked (safer)

### Why This Approach?

**Previous approach was overengineered:**
- 400+ lines of complex "strategy" code
- FAST vs STABLE modes with different behaviors
- Multiple state detection methods with voting
- Network idle detection, persistence verification
- All this complexity tried to check the checkbox early in the form flow

**The fatal flaw:** Checking the checkbox early means subsequent form interactions (like clicking other checkboxes) could trigger React re-renders that uncheck it.

**New approach is simple:**
- ~60 lines of straightforward code
- Single code path (no modes)
- One state detection method (JavaScript `checked` property)
- Verify **right before submission** - nothing can uncheck it after

## Implementation Details

### Single Source of Truth

```python
def _get_mietprofil_checkbox_state(self):
    """JavaScript checked property is what gets submitted"""
    return self.driver.execute_script(
        "return document.getElementById('shareTenantProfile')?.checked || false;"
    )
```

### Human-Like Checking

```python
def _ensure_mietprofil_checked(self):
    """Only clicks if we can confirm it's currently UNCHECKED"""

    # Check current state
    is_checked = self._get_mietprofil_checkbox_state()

    if is_checked is None:
        # Can't determine - skip interaction (safer)
        return True

    if is_checked:
        # Already checked - do nothing
        return True

    # Not checked - need to check it
    label = find_element("label[for='shareTenantProfile']")

    # Scroll into view smoothly (human-like)
    scroll_smooth(label)
    time.sleep(random(0.3, 0.5))

    # Click the label (most reliable for React forms)
    label.click()
    time.sleep(0.3)  # Wait for React update

    # Verify it's now checked
    return self._get_mietprofil_checkbox_state()
```

### Integration in Contact Flow

Located in `send_contact_message()` method:

```python
# After form is ready and submit button is found...

# Final check: Ensure Mietprofil is checked (email forms only)
if form_type == "email":
    if not self._ensure_mietprofil_checked():
        logger.error("Failed to verify Mietprofil - aborting")
        return False

# NOW click submit (checkbox verified)
submit_button.click()
```

## Configuration

**No configuration needed!** The behavior is always active for email forms (company listings).

The old config options have been removed:
- ❌ `willhaben_enforce_mietprofil_sharing` (deleted)
- ❌ `willhaben_mietprofil_stable_mode` (deleted)

## Benefits of New Approach

| Aspect | Old Approach | New Approach |
|--------|--------------|--------------|
| **Lines of code** | 400+ lines | ~60 lines |
| **Complexity** | 3 modes, voting, retries | Single straightforward path |
| **State detection** | 4 methods with voting | 1 method (JavaScript) |
| **Timing** | Early in form flow | Right before submission |
| **Reliability** | Could be unchecked after | Cannot be unchecked after |
| **Debuggability** | Hard to trace failures | Easy to understand |
| **Maintainability** | Fragile, complex | Simple, robust |

## Why It Was Failing Before

1. **Checked too early** - Checkbox verified at line ~780, but submit button clicked at line ~850
2. **React could re-render** - Other form interactions could uncheck it
3. **Never re-verified** - No check right before submission
4. **Overengineered** - Complexity masked the real problem

## HTML Elements Targeted

The checkbox structure:

```html
<label for="shareTenantProfile">
  <input type="checkbox"
         id="shareTenantProfile"
         data-testid="share-tenant-profile-checkbox"
         name="shareTenantProfile">
  <span>Mietprofil teilen</span>
</label>
```

## Logging

**When checkbox is already checked:**
```
INFO: Verifying Mietprofil checkbox before submission...
DEBUG: ✓ Mietprofil already checked
```

**When checkbox needs to be checked:**
```
INFO: Verifying Mietprofil checkbox before submission...
INFO: Mietprofil not checked - checking now...
DEBUG: Clicked Mietprofil label
INFO: ✓ Mietprofil successfully checked
```

**When verification fails:**
```
INFO: Verifying Mietprofil checkbox before submission...
ERROR: ✗ Mietprofil still not checked after click
ERROR: Failed to verify Mietprofil checkbox - aborting submission
```

## Files Modified

1. **`flathunter/willhaben_contact_bot.py`**
   - Removed: `_wait_for_network_idle()`, `_get_comprehensive_checkbox_state()`, `_verify_checkbox_state_persistence()`, `_ensure_element_in_viewport()`, `_enforce_mietprofil_checkbox()`
   - Added: `_get_mietprofil_checkbox_state()`, `_ensure_mietprofil_checked()`
   - Updated: `send_contact_message()` to verify checkbox right before submission
   - Removed: `enforce_mietprofil_sharing` and `mietprofil_stable_mode` parameters

2. **`flathunter/willhaben_contact_processor.py`**
   - Removed config reading for old enforcement settings
   - Simplified bot initialization (no mode parameters)

3. **`config_mietprofil_example.yaml`**
   - Updated documentation to reflect new approach

## Troubleshooting

If tenant profile sharing still fails:

1. **Check account setup** - Ensure your Mietprofil is complete on willhaben.at
2. **Verify login** - Make sure cookies are valid and you're actually logged in
3. **Check form type** - Mietprofil checkbox only exists on email forms (company listings), not messaging forms (private listings)
4. **Review logs** - Check if checkbox verification succeeded before submission

The new simple approach makes debugging much easier - if it fails, you'll know exactly why.
