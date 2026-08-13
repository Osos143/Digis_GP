# NetFix AI thesis patch

Copy these files into `Project_Summary_and_Guidlines/`.

## Files intentionally changed/provided
- `main.tex` - final-defense title page and thesis structure.
- `thesis_setup.tex` - shared professional formatting and chapter-title styling.
- `FrontMatter/Project_Overview.tex` - short platform/business motivation before the technical chapters.
- `Chapters/Anomaly_Detection.tex` - completed anomaly-detection chapter only.
- `Figures/` - figures used by the anomaly chapter.
- `.gitignore` - prevents LaTeX build artifacts and local compile settings from causing Git conflicts.

No RCA, Planning Intelligence, or Integration chapter content is included or overwritten.

## Recommended Git workflow
1. One maintainer owns `main.tex` and `thesis_setup.tex` after this patch is merged.
2. Each team member edits only their own `Chapters/<chapter>.tex` file whenever possible.
3. Give new figures unique, chapter-specific names instead of overwriting a teammate's figure.
4. To compile only one chapter locally, create an untracked `local_includeonly.tex` containing, for example:

```tex
\includeonly{Chapters/Anomaly_Detection}
```

The file is already ignored by `.gitignore`, so authors can compile their own chapter without editing `main.tex`.

## Figure paths
The shared setup uses:

```tex
\graphicspath{{Figures/}{Images/}}
```

The `\projectfigure` macro also shows a visible placeholder if a collaborator has not pulled a referenced figure yet, instead of failing the complete build immediately.
