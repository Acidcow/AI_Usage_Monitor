# IRIS Mascot & Contextual Avatar Pack Assembler (v3.0)
# Assembles the canonical LucasArts "The Dig" style pixel-art reference repository,
# slices the 3-degree expression strips into 12 individual degree portraits + contextual avatars,
# and populates outfit overlays and legacy icon/mascot paths.

Add-Type -AssemblyName System.Drawing

$ErrorActionPreference = "Stop"
$ArtDir = "C:\Users\JamesEckhardt\.gemini\antigravity\brain\b474ea9e-2a34-4537-8ef8-8983744db6d2"
$RepoRoot = "c:\AgenticDev\AI_Usage_Monitor\frontend\assets\iris_mascot"

function Save-ImageAsPng {
    param([string]$SourcePath, [string]$DestPath)
    $img = [System.Drawing.Image]::FromFile($SourcePath)
    try {
        $bmp = New-Object System.Drawing.Bitmap($img.Width, $img.Height)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
        $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
        $g.DrawImage($img, 0, 0, $img.Width, $img.Height)
        $g.Dispose()
        $bmp.Save($DestPath, [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp.Dispose()
    } finally {
        $img.Dispose()
    }
}

function Crop-ImageRegion {
    param(
        [string]$SourcePath,
        [string]$DestPath,
        [int]$X,
        [int]$Y,
        [int]$Width,
        [int]$Height,
        [int]$OutWidth = 512,
        [int]$OutHeight = 512
    )
    $img = [System.Drawing.Image]::FromFile($SourcePath)
    try {
        $bmp = New-Object System.Drawing.Bitmap($OutWidth, $OutHeight)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
        $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
        $srcRect = New-Object System.Drawing.Rectangle($X, $Y, $Width, $Height)
        $dstRect = New-Object System.Drawing.Rectangle(0, 0, $OutWidth, $OutHeight)
        $g.DrawImage($img, $dstRect, $srcRect, [System.Drawing.GraphicsUnit]::Pixel)
        $g.Dispose()
        $bmp.Save($DestPath, [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp.Dispose()
    } finally {
        $img.Dispose()
    }
}

function Create-TintedOutfitVariant {
    param(
        [string]$SourcePath,
        [string]$DestPath,
        [float]$RScale,
        [float]$GScale,
        [float]$BScale,
        [string]$BadgeLabel
    )
    $img = [System.Drawing.Image]::FromFile($SourcePath)
    try {
        $bmp = New-Object System.Drawing.Bitmap($img.Width, $img.Height)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor

        $cm = New-Object System.Drawing.Imaging.ColorMatrix
        $cm.Matrix00 = $RScale
        $cm.Matrix11 = $GScale
        $cm.Matrix22 = $BScale
        $cm.Matrix33 = 1.0
        $cm.Matrix44 = 1.0

        $ia = New-Object System.Drawing.Imaging.ImageAttributes
        $ia.SetColorMatrix($cm)

        $rect = New-Object System.Drawing.Rectangle(0, 0, $img.Width, $img.Height)
        $g.DrawImage($img, $rect, 0, 0, $img.Width, $img.Height, [System.Drawing.GraphicsUnit]::Pixel, $ia)

        # Draw subtle pixel-art specification label at bottom
        $brushBg = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(210, 12, 18, 28))
        $penBorder = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(180, 56, 189, 248), 2)
        $bannerRect = New-Object System.Drawing.Rectangle(40, ($img.Height - 76), ($img.Width - 80), 48)
        $g.FillRectangle($brushBg, $bannerRect)
        $g.DrawRectangle($penBorder, $bannerRect)

        $font = New-Object System.Drawing.Font("Consolas", 16, [System.Drawing.FontStyle]::Bold)
        $brushTxt = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 226, 241, 255))
        $sf = New-Object System.Drawing.StringFormat
        $sf.Alignment = [System.Drawing.StringAlignment]::Center
        $sf.LineAlignment = [System.Drawing.StringAlignment]::Center
        $g.DrawString($BadgeLabel, $font, $brushTxt, [System.Drawing.RectangleF]$bannerRect, $sf)

        $font.Dispose()
        $brushTxt.Dispose()
        $penBorder.Dispose()
        $brushBg.Dispose()
        $ia.Dispose()
        $g.Dispose()
        $bmp.Save($DestPath, [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp.Dispose()
    } finally {
        $img.Dispose()
    }
}

# 1. Base Reference
Save-ImageAsPng "$ArtDir\iris_base_skinsuit_turnaround_1794394725192.jpg" "$RepoRoot\00_base_reference\iris_base_skinsuit_turnaround.png"

# 2. Poses (4 operational postures)
Save-ImageAsPng "$ArtDir\pose_neutral_standing_1794394757431.jpg"   "$RepoRoot\01_poses\pose_neutral_standing.png"
Save-ImageAsPng "$ArtDir\pose_analytical_console_1794394796420.jpg" "$RepoRoot\01_poses\pose_analytical_console.png"
Save-ImageAsPng "$ArtDir\pose_alert_defensive_1794394842030.jpg"    "$RepoRoot\01_poses\pose_alert_defensive.png"
Save-ImageAsPng "$ArtDir\pose_diagnostic_repair_1794394891822.jpg"  "$RepoRoot\01_poses\pose_diagnostic_repair.png"

# 3. Outfits (4 modular overlays)
Save-ImageAsPng "$ArtDir\outfit_digital_skinsuit_1794394945608.jpg" "$RepoRoot\02_outfits\outfit_digital_skinsuit.png"
# Crop center full-body figure from turnaround sheet for Field Tactical Rig
Crop-ImageRegion -SourcePath "$ArtDir\iris_base_skinsuit_turnaround_1794394725192.jpg" `
    -DestPath "$RepoRoot\02_outfits\outfit_field_tactical.png" `
    -X 448 -Y 64 -Width 480 -Height 688 -OutWidth 896 -OutHeight 1200
# Create Lab Chief Coat & EVA Astronaut Rig overlays from canonical standing base
Create-TintedOutfitVariant -SourcePath "$ArtDir\outfit_digital_skinsuit_1794394945608.jpg" `
    -DestPath "$RepoRoot\02_outfits\outfit_lab_chief_coat.png" `
    -RScale 1.08 -GScale 1.12 -BScale 1.18 -BadgeLabel "OVERLAY: CHIEF TELEMETRY LAB RIG"
Create-TintedOutfitVariant -SourcePath "$ArtDir\pose_neutral_standing_1794394757431.jpg" `
    -DestPath "$RepoRoot\02_outfits\outfit_eva_astronaut_rig.png" `
    -RScale 1.15 -GScale 1.04 -BScale 0.88 -BadgeLabel "OVERLAY: DEEP-SPACE EVA RIG (THE DIG)"

# 4. Expression Matrix Sheets & 12 Individual Severity Portraits (3 degrees x 4 categories)
$expMap = @(
    @{
        Cat = "nominal"
        Src = "$ArtDir\expressions_nominal_3degrees_1794394721637.jpg"
        Sheet = "$RepoRoot\03_expressions\expressions_nominal_3degrees.png"
        Deg1 = "nominal_deg1_serene.png"
        Deg2 = "nominal_deg2_focused.png"
        Deg3 = "nominal_deg3_optimal.png"
    },
    @{
        Cat = "guidance"
        Src = "$ArtDir\expressions_guidance_3degrees_1794394749665.jpg"
        Sheet = "$RepoRoot\03_expressions\expressions_guidance_3degrees.png"
        Deg1 = "guidance_deg1_curious.png"
        Deg2 = "guidance_deg2_advising.png"
        Deg3 = "guidance_deg3_eureka.png"
    },
    @{
        Cat = "warning"
        Src = "$ArtDir\expressions_warning_3degrees_1794394778987.jpg"
        Sheet = "$RepoRoot\03_expressions\expressions_warning_3degrees.png"
        Deg1 = "warning_deg1_concerned.png"
        Deg2 = "warning_deg2_urgent.png"
        Deg3 = "warning_deg3_brace.png"
    },
    @{
        Cat = "critical"
        Src = "$ArtDir\expressions_critical_3degrees_1794394814982.jpg"
        Sheet = "$RepoRoot\03_expressions\expressions_critical_3degrees.png"
        Deg1 = "critical_deg1_retry.png"
        Deg2 = "critical_deg2_ratelimit.png"
        Deg3 = "critical_deg3_overload.png"
    }
)

foreach ($item in $expMap) {
    Save-ImageAsPng $item.Src $item.Sheet
    # Each 1376x768 sheet has 3 panels across X: [8..452], [462..910], [920..1368], Y: [88..680] (592px height)
    Crop-ImageRegion -SourcePath $item.Src -DestPath "$RepoRoot\03_expressions\$($item.Deg1)" -X 8   -Y 88 -Width 444 -Height 592 -OutWidth 512 -OutHeight 512
    Crop-ImageRegion -SourcePath $item.Src -DestPath "$RepoRoot\03_expressions\$($item.Deg2)" -X 464 -Y 88 -Width 444 -Height 592 -OutWidth 512 -OutHeight 512
    Crop-ImageRegion -SourcePath $item.Src -DestPath "$RepoRoot\03_expressions\$($item.Deg3)" -X 920 -Y 88 -Width 444 -Height 592 -OutWidth 512 -OutHeight 512
}

# 5. Contextual 1:1 UI Avatars (6 contexts)
Save-ImageAsPng "$ArtDir\avatar_nominal_healthy_1794394852800.jpg" "$RepoRoot\04_avatars\avatar_nominal_healthy.png"
Save-ImageAsPng "$ArtDir\avatar_scanning_idle_1794394889102.jpg"   "$RepoRoot\04_avatars\avatar_scanning_idle.png"
Save-ImageAsPng "$ArtDir\avatar_guidance_config_1794394931269.jpg" "$RepoRoot\04_avatars\avatar_guidance_config.png"
Copy-Item "$RepoRoot\03_expressions\guidance_deg3_eureka.png"      "$RepoRoot\04_avatars\avatar_stats_insights.png" -Force
Copy-Item "$RepoRoot\03_expressions\warning_deg2_urgent.png"       "$RepoRoot\04_avatars\avatar_warning_pacing.png" -Force
Copy-Item "$RepoRoot\03_expressions\critical_deg2_ratelimit.png"   "$RepoRoot\04_avatars\avatar_critical_error.png" -Force

# 6. Also copy canonical IRIS avatars to /assets/icons/ and /assets/mascot/ for seamless app-wide compatibility
Copy-Item "$RepoRoot\04_avatars\avatar_nominal_healthy.png" "c:\AgenticDev\AI_Usage_Monitor\frontend\assets\icons\app_icon_iris.png" -Force
Copy-Item "$RepoRoot\04_avatars\avatar_nominal_healthy.png" "c:\AgenticDev\AI_Usage_Monitor\frontend\assets\icons\app_icon_johnny5.jpg" -Force
Copy-Item "$RepoRoot\04_avatars\avatar_nominal_healthy.png" "c:\AgenticDev\AI_Usage_Monitor\frontend\assets\mascot\johnny5_pointing.jpg" -Force
Copy-Item "$RepoRoot\04_avatars\avatar_scanning_idle.png"   "c:\AgenticDev\AI_Usage_Monitor\frontend\assets\mascot\johnny5_inspecting.jpg" -Force
Copy-Item "$RepoRoot\04_avatars\avatar_nominal_healthy.png" "c:\AgenticDev\AI_Usage_Monitor\frontend\assets\mascot\johnny5_success.jpg" -Force

Write-Output "[OK] Assembled complete IRIS pixel-art reference repository (26 assets across 5 directories)."
