# Collision Detection Debugging Guide

## Quick Start: Find the ROOT CAUSE

### Step 1: Quick Diagnosis (Run First)
```bash
cd c:\Users\visha\OneDrive\Desktop\Aegis_Hack\Aegis_coep
python -m detection.quick_diagnose path_to_your_video.mp4
```

**This tells you:**
- ✓ Are vehicles being detected at all?
- ✓ Are vehicle pairs forming?
- ✓ How close do vehicles get?

**STOP HERE if:**
- ❌ No vehicles detected → YOLO problem (model file missing?)
- ❌ No pairs forming → Tracking issue (ByteTrack IDs broken?)

---

### Step 2: Full Debug (If Step 1 passes)
```bash
python -m detection.debug_collisions path_to_your_video.mp4
```

**This shows:**
- ✓ Every vehicle pair scored
- ✓ Why each pair is accepted/rejected
- ✓ Exact score breakdown
- ✓ Validator state frame-by-frame

**Look for:**
```
[1] #123-#456 car vs car
    Distance: 45.2px | Cutoff: 200.0px ✓
    Score: 0.382 [bbox=0.15 dist=0.85 accel=0.00 chaos=0.05]
    ✗ Below threshold (0.40)
```

This shows the score (0.382) is ALMOST there but below 0.40.

---

## Common Issues & Fixes

### Issue #1: "NO VEHICLES DETECTED"
```
❌ Vehicle detection: 0% of frames
```
**Solutions:**
```python
# A) Model file missing
   Expected: c:\Users\visha\OneDrive\Desktop\Aegis_Hack\Aegis_coep\yolov8m.pt
   
# B) Model still loading from internet
   → First run downloads model automatically (might take 5 min)
   → Try again
   
# C) YOLO configuration broken
   → Try: from ultralytics import YOLO; YOLO("yolov8m.pt")
```

---

### Issue #2: "VEHICLES DETECTED BUT NO PAIRS"
```
Average pairs per frame: 0.0
```
**Solution:**
- Check if ByteTrack IDs are being assigned
- Vehicles need DIFFERENT track_ids to form pairs
- Check: `box.id is not None` in _extract_vehicles()

---

### Issue #3: "PAIRS FORM BUT SCORES ARE TOO LOW"
```
[1] #123-#456 car vs car
    Distance: 45.2px
    Score: 0.25 ✗ Below threshold (0.40)
```

**Solutions:**

A) **Proximity not helping** (distance still low)
   ```python
   # Current at bottom of _pair_score():
   if centre_dist < 100:
       score = max(score, 0.7)
   
   # Make it more aggressive:
   if centre_dist < 120:
       score = max(score, 0.75)
   if centre_dist < 80:
       score = max(score, 0.85)
   ```

B) **Chaos is zero**
   ```python
   # Check if optical flow is working
   # If chaos_s ≈ 0 always → motion detection broken
   ```

C) **Threshold is still too high**
   ```python
   # Current: SCORE_THRESHOLD = 0.40
   # Try: SCORE_THRESHOLD = 0.35
   ```

---

### Issue #4: "SCORES LOOK GOOD BUT VALIDATOR NEVER CONFIRMS"
```
Validator state after update: 1/2
Confirmed: False
(next frame)
Validator state after update: 0/2
Confirmed: False
```

**Problem:** Validator keeps resetting
- Need 2 consecutive frames with score > 0.40
- If score > 0.40 on frame N but < 0.40 on frame N+1, counter resets to 0

**Solutions:**

A) **Lower threshold slightly**
   ```python
   SCORE_THRESHOLD = 0.35  # was 0.40
   ```

B) **Make proximity trigger even stronger**
   ```python
   # Make sure close vehicles ALWAYS pass
   if centre_dist < 100:
       score = max(score, 0.8)  # was 0.7
   ```

C) **Reduce confirm_frames requirement**
   ```python
   # In detector.py __init__:
   self.accident_detector = AccidentDetector(
       confirm_frames=1, debug=acc_debug  # was 2
   )
   ```

---

## Debug Output Interpretation

### Good Sign ✅
```
[2] #101-#102 car vs car
    Distance: 55.3px | Cutoff: 200.0px ✓
    ✓ Both stopped, BUT close (<100px) → CONTINUE
    Score: 0.72 [bbox=0.25 dist=0.95 accel=0.00 chaos=0.12]
    ✓ THRESHOLD PASSED → EVENT ADDED

Validator state after update: 2/2
Confirmed: True
✓ COLLISION CONFIRMED AND REPORTED
```

### Bad Sign ❌
```
[1] #101-#102 car vs car
    Distance: 250.0px | Cutoff: 200.0px ✗ TOO FAR
    
[2] #103-#104 car vs car
    Distance: 55.3px
    Score: 0.28 [bbox=0.05 dist=0.45 accel=0.00 chaos=0.02]
    ✗ Below threshold (0.40)

Events detected: 0
Validator state before: 0/2
Flagged: False
```

This shows:
- Pair 1: Too far (distance filter is working)
- Pair 2: Score too low (scoring itself too conservative)
- Validator: Never gets flagged=True, so never confirms

---

## The Most Likely Issue Right Now

Given you've already tuned all the constants, the problem is probably:

**TL;DR: The validator is being reset somewhere unintended, OR the consecutive-frame requirement is too strict for your video**

Try:
```python
# In detector.py
self.accident_detector = AccidentDetector(
    confirm_frames=1  # Changed from 2
)

# In incident_detectors.py
SCORE_THRESHOLD = 0.35  # Changed from 0.40
```

Then test again.

---

## Need More Help?

Run the diagnostic and paste the output. The patterns will tell us exactly where to fix.
