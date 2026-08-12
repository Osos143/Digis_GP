# NetFix — Simple User Guide

## A beginner-friendly guide to using the 5G Network Planning workspace

---

## 1. What is NetFix?

**NetFix** is a 5G network planning workspace that helps you:

- Upload your network data
- Generate PCI, Mod4, Mod3 and RSI assignments
- Check planning problems
- Understand clashes
- View the network on a map
- Replan an existing site
- Add a new site
- Compare planning results
- Ask the AI Assistant about the network

You do **not** need to understand the planning algorithm to use the tool.

---

## 2. Start the Application

Open NetFix and select:

> **5G Network Planning**

You will then enter the main planning workspace.

The main sections are:

1. **Upload & Plan**
2. **Planning**
3. **Clashes**
4. **Assignments**
5. **Add Site**
6. **AI Assistant**
7. **Voronoi Compare**

---

## 3. Step 1 — Upload Your Excel File

Go to:

> **Upload & Plan**

You have two choices.

### Option A — Raw Workbook

Choose this when your Excel file still needs planning.

Select **Raw Workbook** and upload your Excel file.

NetFix will:

**Upload → Plan → Validate → Create the planned result**

After planning finishes, the new planned workbook becomes your active network.

### Option B — Already Planned Workbook

Choose this when your Excel file already contains assignments.

Select **Already Planned** and upload the file.

NetFix will load the existing plan and check its results.

### Simple rule

| Your file | Choose |
|---|---|
| Network still needs planning | **Raw** |
| Network already has assignments | **Already Planned** |

---

## 4. Step 2 — Check the Planning Dashboard

After uploading/planning, open:

> **Planning**

This is your main overview.

You can quickly see:

- Number of sites
- Number of sectors
- Planning status
- Hard problems
- Soft conflicts
- Regional information
- Network map

### What should I check first?

Look at the overall result:

**PASS** → the plan satisfies the required hard rules.

**FAIL** → there are still hard planning problems that need attention.

---

## 5. Step 3 — Look at the Network Map

The map gives you a visual view of the network.

Available views can include:

- PCI
- Mod4
- Mod3
- RSI
- Regions
- Sector directions
- Clashes

Use the map when you want to answer:

> **"Where is this problem happening?"**

---

## 6. Step 4 — Investigate Clashes

If the plan contains problems, open:

> **Clashes**

This page helps you find and understand network conflicts.

You can filter results by:

- Region
- Clash type
- Sector
- Site

You do not need to inspect the whole network. Start with the sectors or sites showing problems.

### Main clash types

**PCI Collision**  
Two nearby sectors are using the same PCI where they should not.

**PCI Confusion**  
Two sectors farther apart are using the same PCI and may cause confusion.

**RSI Reuse**  
The same RSI is being reused where it should not be.

**Mod3 Clash**  
Two sectors on the same site have an unsuitable Mod3 relationship.

**Mod4 Clash**  
Two sectors have an undesirable Mod4 relationship.

The tool detects these automatically.

---

## 7. Check Why a Sector Has a Problem

In **Clashes**, search for a sector and select it.

NetFix can show:

- PCI
- Mod3
- Mod4
- RSI
- Nearby sectors
- Distances
- Detected conflicts
- An explanation of the problem

This answers:

> **"Why is this sector causing a problem?"**

You do not need to calculate the distances or check the PCI values yourself.

---

## 8. Step 5 — Check Assignments

Open:

> **Assignments**

This page shows detailed planning information for the sectors.

You can inspect:

- Site
- Sector
- PCI
- Mod3
- Mod4
- RSI
- Region
- Clash status

You can also search, filter and sort the table.

Use this page when you want to inspect the exact assigned values.

---

## 9. Step 6 — Replan an Existing Site

Sometimes you want to change the planning of one existing site.

Go to:

> **Add Site → Replan Existing Site**

Select the site you want to change.

NetFix will show the current planning and provide new options.

### Guided Site Replanning

You can work through the choices step by step:

**Mod4 → Mod3 → PCI**

The available PCI choices are updated according to your selections.

You do not need to manually search through all possible PCI values.

When you are satisfied, commit the changes.

The rest of the network remains unchanged.

---

## 10. Step 7 — Add a New Site

To add a completely new site:

> **Add Site → Add Brand-New Site**

Enter:

- Site ID
- Site location
- Sector directions

You can use the map to select the location.

NetFix will show the nearby network and generate proposed assignments.

You can review:

- PCI
- Mod4
- RSI
- Nearby sectors

If everything looks good, commit the new site.

The new planned network becomes your active network.

---

## 11. Step 8 — Use the AI Assistant

Open:

> **AI Assistant**

Ask questions using normal language.

Examples:

> Why does ALX001_2 have a clash?

> Show me the neighbors of this sector.

> Which sites have the most clashes?

> What is the difference between PCI collision and PCI confusion?

> Explain this planning result.

The AI Assistant uses the actual planning data to help explain the result.

It is mainly there to **help you understand the planning output**, not to replace the planning engine.

---

## 12. Step 9 — Compare Planning Results

Open:

> **Voronoi Compare**

Use this when you want to visually compare network planning before and after a change.

For example:

**Before** → Existing network

**After** → New or optimized network

The comparison helps you understand how a planning change affects the surrounding area.

---

## 13. A Normal Work Session

For most users, the recommended workflow is:

1. **Upload** the Excel file
2. **Run or load** the planning
3. Open **Planning**
4. Check **PASS / FAIL**
5. Look at the **map**
6. Open **Clashes** if there are problems
7. Investigate problematic sectors
8. Check **Assignments** for detailed values
9. **Replan a site** or **add a new site** if needed
10. **Compare** the result
11. Use **AI Assistant** when you need an explanation

---

## 14. What You Need to Remember

| If you want to... | Go to... |
|---|---|
| Upload a network | **Upload & Plan** |
| See the overall result | **Planning** |
| Find problems | **Clashes** |
| Inspect exact values | **Assignments** |
| Change an existing site | **Add Site → Replan Existing Site** |
| Add a new site | **Add Site → Add Brand-New Site** |
| Ask a question | **AI Assistant** |
| Compare planning | **Voronoi Compare** |

---

## 15. Important Tips

### Start with the dashboard

You do not need to inspect every sector immediately.

### Use the map to understand location

Use the tables when you need exact values.

### Use Clashes to investigate problems

You do not need to calculate conflicts yourself.

### Use the AI Assistant for explanations

Ask questions in normal language.

### Use Raw vs. Already Planned correctly

- **Raw** = the network needs planning.
- **Already Planned** = assignments already exist.

---

## 16. The Complete Workflow

```text
             UPLOAD
                ↓
              PLAN
                ↓
          CHECK RESULT
                ↓
       ┌────────┴────────┐
       ↓                 ↓
      MAP             CLASHES
       ↓                 ↓
 Understand          Find Problems
 the Network              ↓
                     Investigate
                         ↓
                  ┌──────┴──────┐
                  ↓             ↓
               REPLAN        ADD SITE
                  ↓             ↓
                  └──────┬──────┘
                         ↓
                     COMPARE
                         ↓
                  AI ASSISTANT
```

---

## 17. In One Sentence

> **NetFix takes your network data, creates a planning result, shows you where problems are, helps you understand them, and lets you safely modify the network when needed.**
