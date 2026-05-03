# 🚀 Production Fix Plan — Complete Action Steps

**Status**: Ready to implement  
**Issue**: Mandi prices not showing + AI enrichment not working  
**Root Cause**: Test farmer has NO CROPS registered  

---

## **IMMEDIATE FIX (30 minutes)**

### **1. Delete Incomplete Test Farmer**

The test farmer never completed registration (missing crops step).

```bash
# Connect to Railway Postgres
railway shell --service Postgres

# Then run:
psql $DATABASE_URL << 'EOF'

-- Soft delete farmers with no crops (incomplete registrations)
UPDATE farmers SET deleted_at = NOW() 
WHERE deleted_at IS NULL 
AND id NOT IN (SELECT DISTINCT farmer_id FROM crops_of_interest);

-- Verify
SELECT id, phone, name, district, subscription_status FROM farmers WHERE deleted_at IS NULL;
EOF
```

**Expected result**: Empty or only farmers with crops

---

### **2. Re-Register Farmer (WITH CROPS)**

When farmer sends "Hi", they'll go through 3-step registration:

**Step 1: Name**
```
Bot: नमस्कार! आजचे शेतकरी माहिती सेवा येथे आपले स्वागतं.
     कृपया आपले पूर्ण नाव सांगा.

Farmer: राज कुमार
```

**Step 2: Village**
```
Bot: आपले गाव कोणते?
     (LOCATION PARSER will auto-detect district)

Farmer: परनेर
```

**Step 3: CROPS (CRITICAL!)**
```
Bot: आपण कोणती पिके घेवतात?
     उदा: कांदा, सोयाबीन, तूर, गहू, कापूस

Farmer: कांदा, तूर, सोयाबीन
```

**Expected bot response:**
```
🎉 नोंदणी पूर्ण झाली, राज!
📍 गाव: परनेर, अहिल्यानगर
🌾 पिके: कांदा, तूर, सोयाबीन

दर रोज सकाळी ७ वाजता शेतकरी माहिती पत्र मिळेल.
```

---

### **3. Verify Crop Registration**

Check database:

```bash
railway shell --service Postgres

psql $DATABASE_URL << 'EOF'
-- Check newly registered farmer
SELECT id, name, district, subscription_status 
FROM farmers 
WHERE subscription_status = 'active' 
AND deleted_at IS NULL;

-- Check their crops
SELECT c.crop 
FROM crops_of_interest c 
WHERE c.farmer_id = (SELECT id FROM farmers WHERE name LIKE '%राज%' LIMIT 1);
EOF
```

**Expected result:**
```
 crop      
-----------
 कांदा
 तूर
 सोयाबीन
```

---

### **4. Trigger Advisory Generation**

Once crops are registered, advisories will generate at 6:45 AM daily.  
To test NOW:

```bash
# Get fresh admin token
curl -s -X POST "https://kisan-ai-production-6f73.up.railway.app/admin/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=changeme" | jq -r '.access_token'

# Save token and trigger
TOKEN="<paste-token-here>"
curl -s -X POST "https://kisan-ai-production-6f73.up.railway.app/admin/advisory/api/run-now" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**Expected output:**
```json
{
  "farmers": 1,
  "total_created": 2,  ← Should be > 0!
  "by_farmer": {
    "123": 2
  }
}
```

---

### **5. Verify AI Enrichment**

Check logs:

```bash
railway logs --service kisan-ai 2>&1 | grep -i "ai_enrichment\|enrichment success" | tail -10
```

**Expected logs:**
```
INFO:src.advisory.engine:advisory_engine: AI enrichment success for rule=fungal_disease model=meta/llama-3.1-8b-instruct:free
INFO:src.advisory.engine:advisory_engine: AI enrichment success for rule=irrigation_alert model=meta/llama-3.1-8b-instruct:free
```

---

### **6. Test Full Daily Brief**

Send "Hi" and verify all 4 parts:

**Part 1: Weather** ✅ (Already working)
```
🌤️ हवामान — परनेर, अहिल्यानगर
तापमान: 28-35°C
आर्द्रता: 72%
...
```

**Part 2: MANDI PRICES** ✅ (Should now work)
```
💰 आजचे APMC मंडी भाव — महाराष्ट्र (₹/क्विंटल)

कांदा     : ₹800 | ₹850 | ₹900 ⚠️
तूर       : ₹7045 | ₹7105 | ₹7390
सोयाबीन   : ₹4210 | ₹4210 | ₹4210

📍 भाव कोठून आले:
  कांदा — पुणे (पिंपरी APMC)
  तूर — amarawati (वरूड APMC)
  सोयाबीन — amarawati (वरूड APMC)
```

**Part 3: AI ADVISORY** ✅ (Should NOW WORK!)
```
🦠 रोग व कीड सतर्कता — AI विश्लेषण

⚠️ कांद्यात फुलकिडे जोखीम
आर्द्रता 72% > 70% (उच्च जोखीम)

🤖 AI सुझाव:
- थंड पाणी दिवसातून २-३ वेळा द्या
- बोर्डो मिश्रण १% फवारा (सकाळी ६-७ वाजता)
- पानांवरील ओलावा दूर करा

उपाय: फिप्रोनिल ५% SC @ २ मिली/लिटर
```

**Part 4: Irrigation** ✅ (Already working)
```
💧 सिंचन योजना
अग्नीमानार्थ सिंचन सूचित: ३-४ दिवसांत
कारण: अंदाज: २-४ मिमी पाऊस
```

---

## **NEXT: Chatbot Functionality (After data is fixed)**

### **Where to Add Q&A**

File: `src/main.py` (line ~293+)

Current code:
```python
elif intent_type == Intent.PEST_QUERY:
    # Route to pest handler
    
elif intent_type == Intent.PRICE_QUERY:
    # Route to price handler
```

**Add new section:**
```python
elif intent_type == Intent.GENERAL_QUESTION:
    # Route to AI Q&A handler
    response = await handle_general_question(
        farmer=farmer,
        question=msg.text,
        session=db_session
    )
    await send_message(response)
```

### **What to Implement**

1. **New Intent**: `GENERAL_QUESTION`
   - Detect questions like:
     - "बीज कोणते वापरू?"
     - "कीटकनाशक कसे फवारू?"
     - "कर्जाच्या योजनाबाबत?"

2. **Intent Classifier Update**: `src/classifier/intents.py`
   ```python
   GENERAL_QUESTION = "general_question"  # New intent
   ```

3. **Classifier Pattern**: `src/classifier/llm_classifier.py`
   ```python
   # Add pattern to detect general questions
   if any(word in text.lower() for word in ['कसे', 'काय', 'कोणते', 'कुठे']):
       return Intent.GENERAL_QUESTION
   ```

4. **Handler**: Create `src/handlers/qa_handler.py`
   ```python
   async def handle_general_question(farmer, question, session):
       """Answer general farming questions with AI."""
       
       response = await enrich_advisory_with_ai(
           rule_type="general_qa",
           farmer_crops=farmer.crops,
           question=question,
           district=farmer.district,
       )
       
       return format_marathi_response(response)
   ```

5. **Use Existing LLM Function**:
   - Reuse `src/advisory/ai_enrichment.py` 
   - Call with appropriate prompt for Q&A

---

## **Testing Checklist**

Before considering "FIXED":

- [ ] Farmer deleted from database
- [ ] New farmer registered with crops
- [ ] Crops visible in `crops_of_interest` table
- [ ] Advisory generation creates > 0 advisories
- [ ] AI enrichment logs show "success"
- [ ] Part 2 (Mandi Prices) displays in daily brief
- [ ] Part 3 (AI Advisory) shows AI-enriched guidance
- [ ] Farmer can ask "हवामान काय आहे?" and get response
- [ ] Farmer can ask "कांद्याच्या रोगांविषयी सांग" and get AI guidance

---

## **Expected Results After Fix**

### **Current State** (Before)
```
Part 1: Weather ✅
Part 2: Mandi Prices ✅ (but May 1st is correct!)
Part 3: AI Advisory ❌ (Generic fallback only)
Part 4: Irrigation ✅
Chatbot Q&A ❌
```

### **After Fix** (With crops registered)
```
Part 1: Weather ✅
Part 2: Mandi Prices ✅ (Shows current market prices)
Part 3: AI Advisory ✅ (Crop-specific AI guidance!)
Part 4: Irrigation ✅
Chatbot Q&A ✅ (Ask general questions)
```

---

## **Timeline**

| Step | Action | Time |
|------|--------|------|
| 1 | Delete incomplete farmer | 2 min |
| 2 | Re-register with crops | 5 min |
| 3 | Verify in database | 2 min |
| 4 | Trigger advisory generation | 2 min |
| 5 | Check AI enrichment logs | 2 min |
| 6 | Test daily brief | 5 min |
| **Total Immediate Fix** | | **18 min** |
| 7 | Add chatbot Q&A (optional) | 30-60 min |

---

## **Support**

If anything fails:

1. **No advisories created**: Check if farmer has crops
   ```bash
   SELECT crop FROM crops_of_interest WHERE farmer_id = X;
   ```

2. **AI enrichment failing**: Check OpenRouter API key
   ```bash
   railway logs --service kisan-ai 2>&1 | grep -i "openrouter\|api_key"
   ```

3. **Daily brief not sending**: Check if farmer subscribed
   ```bash
   SELECT subscription_status FROM farmers WHERE id = X;
   ```

---

**Ready? Let's go! 🚀**

