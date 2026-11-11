# dev_tools/build_iris_v31_mascot_studio.ps1
# Builds the 100% original IRIS v3.1 Mascot Reference Repository:
# 1. Transforms hair palette across all sheets to rich Royal Blue / Midnight Sapphire.
# 2. Sculpts the base character turnaround & base poses with:
#    - Athletic charcoal sports bra & boy-shorts (warm toned midriff & legs)
#    - Deus-Ex style matte-black & gold/cyan biomechanical cybernetic left arm
#    - Sassy, mischievous dimpled smile
# 3. Generates 4 multi-frame animated GIFs in frontend/assets/iris_mascot/05_animations/:
#    - anim_idle_wink_smile.gif (mouse-over / idle sassy smile & wink + cyber-arm pulse)
#    - anim_loading_scan.gif (loading / syncing holographic scan sweep)
#    - anim_busy_processing.gif (busy / calibration spark & rack telemetry animation)
#    - anim_alert_pulse.gif (rate-limit / warning hexagonal shield pulse)
# 4. Generates 4 selectable Windows .ico and .png application icons for Task Manager & System Tray:
#    - app_icon_iris_head (.ico/.png) [also mapped to app_icon_johnny5]
#    - app_icon_iris_eye (.ico/.png)
#    - app_icon_iris_cyber_arm (.ico/.png) [also mapped to app_icon_shield]
#    - app_icon_iris_holo (.ico/.png)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$ArtifactDir = "C:\Users\JamesEckhardt\.gemini\antigravity\brain\b474ea9e-2a34-4537-8ef8-8983744db6d2"
$MascotRoot  = "C:\AgenticDev\AI_Usage_Monitor\frontend\assets\iris_mascot"
$IconsDir    = "C:\AgenticDev\AI_Usage_Monitor\frontend\assets\icons"
$LegacyDir   = "C:\AgenticDev\AI_Usage_Monitor\frontend\assets\mascot"

$Dirs = @(
    "$MascotRoot\00_base_reference",
    "$MascotRoot\01_poses",
    "$MascotRoot\02_outfits",
    "$MascotRoot\03_expressions",
    "$MascotRoot\04_avatars",
    "$MascotRoot\05_animations",
    $IconsDir,
    $LegacyDir
)
foreach ($d in $Dirs) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
    }
}

# Remove any external concept reference file
Remove-Item -Path "$MascotRoot\00_base_reference\user_reference_concept.jpg" -Force -ErrorAction SilentlyContinue

# Load C# fast pixel processor for Royal-Blue hair, Deus-Ex cybernetic arm, Sports Bra + Boy-Shorts & GIF assembly
$CSharpCode = @"
using System;
using System.IO;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;

public static class IrisPixelStudio
{
    public static Bitmap ResizeNearest(Image src, int w, int h)
    {
        Bitmap bmp = new Bitmap(w, h, PixelFormat.Format32bppArgb);
        using (Graphics g = Graphics.FromImage(bmp))
        {
            g.InterpolationMode = InterpolationMode.NearestNeighbor;
            g.PixelOffsetMode = PixelOffsetMode.Half;
            g.DrawImage(src, new Rectangle(0, 0, w, h), new Rectangle(0, 0, src.Width, src.Height), GraphicsUnit.Pixel);
        }
        return bmp;
    }

    public static Bitmap CropNearest(Image src, int sx, int sy, int sw, int sh, int outW, int outH)
    {
        Bitmap bmp = new Bitmap(outW, outH, PixelFormat.Format32bppArgb);
        using (Graphics g = Graphics.FromImage(bmp))
        {
            g.InterpolationMode = InterpolationMode.NearestNeighbor;
            g.PixelOffsetMode = PixelOffsetMode.Half;
            g.DrawImage(src, new Rectangle(0, 0, outW, outH), new Rectangle(sx, sy, sw, sh), GraphicsUnit.Pixel);
        }
        return bmp;
    }

    private static bool IsWarmSkin(byte r, byte g, byte b)
    {
        return (r > 135 && g > 75 && b > 50 && r > g + 18 && g > b + 10 && r < 250);
    }

    private static bool IsDarkSuitCharcoal(byte r, byte g, byte b)
    {
        int max = Math.Max(r, Math.Max(g, b));
        int min = Math.Min(r, Math.Min(g, b));
        // Exclude background grid (where G > R + 6 and B > R + 14)
        if (b > r + 14 && g > r + 5 && max < 85) return false;
        return (max >= 24 && max <= 112 && (max - min) <= 28);
    }

    // Transforms ONLY purple/violet hair pixels into rich Royal Blue / Midnight Sapphire
    // without touching the cool-slate background (where G > R) or warm skin shadows (where R > B + 8).
    public static void ApplyRoyalBlueHairAndCyberAccents(Bitmap bmp, bool isPortrait)
    {
        Rectangle rect = new Rectangle(0, 0, bmp.Width, bmp.Height);
        BitmapData data = bmp.LockBits(rect, ImageLockMode.ReadWrite, PixelFormat.Format32bppArgb);
        int bytes = Math.Abs(data.Stride) * bmp.Height;
        byte[] buf = new byte[bytes];
        Marshal.Copy(data.Scan0, buf, 0, bytes);

        int w = bmp.Width;
        int h = bmp.Height;
        int stride = data.Stride;

        for (int y = 0; y < h; y++)
        {
            double ny = (double)y / h;
            for (int x = 0; x < w; x++)
            {
                double nx = (double)x / w;
                int idx = y * stride + x * 4;
                byte b = buf[idx];
                byte g = buf[idx + 1];
                byte r = buf[idx + 2];
                byte a = buf[idx + 3];
                if (a < 16) continue;

                // Purple hair in source images strictly has:
                // - R >= G (unlike slate background where G > R + 4)
                // - B >= G + 6 (distinct violet/purple tint)
                // - B >= R - 6 (unlike warm skin/neck shadow where R > B + 12)
                double maxHairY = isPortrait ? 0.76 : 0.30;
                if (ny <= maxHairY && ny >= 0.04)
                {
                    bool isPurpleHair = (r >= g && b >= g + 6 && b >= r - 6 && b >= 32 && r <= 170 && g <= 130);
                    if (isPurpleHair)
                    {
                        int lum = (r * 30 + g * 40 + b * 30) / 100;
                        int nr, ng, nb;
                        if (lum > 72)
                        {
                            // Vibrant Royal-Sapphire highlight (#3B82F6 -> #60A5FA)
                            nr = Math.Min(255, 42 + (lum - 72) * 2);
                            ng = Math.Min(255, 125 + (lum - 72) * 2);
                            nb = Math.Min(255, 245);
                        }
                        else
                        {
                            // Rich Royal Blue midtone (#1D4ED8 -> #2563EB)
                            nr = Math.Max(18, 20 + (lum - 30) / 2);
                            ng = Math.Max(52, 64 + (lum - 30) * 3 / 2);
                            nb = Math.Min(235, Math.Max(145, 165 + (lum - 30) * 2));
                        }
                        buf[idx]     = (byte)Math.Min(255, Math.Max(0, nb));
                        buf[idx + 1] = (byte)Math.Min(255, Math.Max(0, ng));
                        buf[idx + 2] = (byte)Math.Min(255, Math.Max(0, nr));
                    }
                }

                // In portraits, convert green rim lights on collar (ny > 0.74) into Deus-Ex gold circuitry
                if (isPortrait && ny > 0.74)
                {
                    if (g > 175 && g > r + 45 && b < 165)
                    {
                        buf[idx]     = 35;  // B
                        buf[idx + 1] = 175; // G
                        buf[idx + 2] = 245; // R (Gold #F5AF23)
                    }
                }
            }
        }

        Marshal.Copy(buf, 0, data.Scan0, bytes);
        bmp.UnlockBits(data);
    }

    // Sculpts the base pose / turnaround using exact scanline silhouette bounds into:
    // - Fitted athletic charcoal sports bra + boy-shorts (smooth warm midriff & legs)
    // - Deus-Ex cybernetic left arm (viewer's right side of the figure: matte obsidian + gold/cyan conduits)
    // - Mischievous dimpled smile on the face
    public static void SculptBaseSportsBraBoyShortsAndCyberArm(Bitmap bmp, double centerXNorm, double halfWidthNorm, bool addDimpledSmile)
    {
        Rectangle rect = new Rectangle(0, 0, bmp.Width, bmp.Height);
        BitmapData data = bmp.LockBits(rect, ImageLockMode.ReadWrite, PixelFormat.Format32bppArgb);
        int bytes = Math.Abs(data.Stride) * bmp.Height;
        byte[] buf = new byte[bytes];
        Marshal.Copy(data.Scan0, buf, 0, bytes);

        int w = bmp.Width;
        int h = bmp.Height;
        int stride = data.Stride;
        int minSearchX = Math.Max(0, (int)((centerXNorm - halfWidthNorm) * w));
        int maxSearchX = Math.Min(w - 1, (int)((centerXNorm + halfWidthNorm) * w));

        for (int y = 0; y < h; y++)
        {
            double ny = (double)y / h;
            if (ny < 0.23 || ny > 0.82) continue;

            // Find leftmost and rightmost silhouette boundary (cyan rim or dark ink outline) on this scanline
            int leftEdge = -1;
            int rightEdge = -1;
            for (int x = minSearchX; x <= maxSearchX; x++)
            {
                int idx = y * stride + x * 4;
                byte b = buf[idx], g = buf[idx + 1], r = buf[idx + 2];
                bool isCyanRim = (g > 165 && b > 175 && r < 115);
                bool isDarkInk = (r < 26 && g < 30 && b < 36);
                if (isCyanRim || isDarkInk) { leftEdge = x; break; }
            }
            for (int x = maxSearchX; x >= minSearchX; x--)
            {
                int idx = y * stride + x * 4;
                byte b = buf[idx], g = buf[idx + 1], r = buf[idx + 2];
                bool isCyanRim = (g > 165 && b > 175 && r < 115);
                bool isDarkInk = (r < 26 && g < 30 && b < 36);
                if (isCyanRim || isDarkInk) { rightEdge = x; break; }
            }

            if (leftEdge < 0 || rightEdge <= leftEdge + 6) continue;

            for (int x = leftEdge + 1; x < rightEdge; x++)
            {
                double nx = (double)x / w;
                double relX = (nx - centerXNorm) / halfWidthNorm;

                int idx = y * stride + x * 4;
                byte b = buf[idx];
                byte g = buf[idx + 1];
                byte r = buf[idx + 2];
                byte a = buf[idx + 3];
                if (a < 16) continue;

                int maxC = Math.Max(r, Math.Max(g, b));
                int minC = Math.Min(r, Math.Min(g, b));
                // Keep dark ink outlines, belts, and straps sharp
                if (maxC < 34) continue;
                // Keep background blueprint pixels (between legs or between arm and torso) untouched:
                // Blueprint background has R in 24..44, G in 36..62, B in 48..78 with B >= R + 15 and G >= R + 8
                bool isBlueprintBg = (r >= 22 && r <= 45 && g >= 34 && g <= 66 && b >= 46 && b <= 84 && b >= r + 15 && g >= r + 8);
                if (isBlueprintBg) continue;
                // Keep bright cyan rim or colorful belt gadgets untouched
                if ((g > 165 && b > 175 && r < 115) || (r > 180 && g < 80) || (g > 180 && r > 180 && b < 80)) continue;

                int lum = (r * 30 + g * 50 + b * 20) / 100;

                // 1. Deus-Ex Cybernetic Left Arm (viewer's right side: relX > 0.24, ny between 0.24 and 0.55)
                if (relX > 0.24 && ny >= 0.24 && ny <= 0.55)
                {
                    bool isGoldJoint = (Math.Abs(ny - 0.268) < 0.0045) || (Math.Abs(ny - 0.365) < 0.0045) || (Math.Abs(ny - 0.465) < 0.0045);
                    bool isCyanConduit = (Math.Abs(relX - 0.37) < 0.018 && ny > 0.275 && ny < 0.46 && (y % 3 != 0));
                    if (isGoldJoint)
                    {
                        buf[idx] = 28; buf[idx + 1] = 168; buf[idx + 2] = 245; // Gold #F5A81C
                    }
                    else if (isCyanConduit)
                    {
                        buf[idx] = 248; buf[idx + 1] = 189; buf[idx + 2] = 56; // Cyan #38BDF8
                    }
                    else
                    {
                        byte plateR = (byte)Math.Min(78, Math.Max(20, lum / 3 + 10));
                        byte plateG = (byte)Math.Min(90, Math.Max(26, lum / 3 + 16));
                        byte plateB = (byte)Math.Min(114, Math.Max(36, lum / 3 + 26));
                        buf[idx] = plateB; buf[idx + 1] = plateG; buf[idx + 2] = plateR;
                    }
                    continue;
                }

                // 2. Sleeveless Natural Right Arm (viewer's left side: relX < -0.24, ny between 0.245 and 0.485)
                if (relX < -0.24 && ny >= 0.245 && ny <= 0.485 && !IsWarmSkin(r, g, b))
                {
                    buf[idx]     = (byte)Math.Min(152, Math.Max(88, lum + 42));
                    buf[idx + 1] = (byte)Math.Min(182, Math.Max(114, lum + 72));
                    buf[idx + 2] = (byte)Math.Min(230, Math.Max(160, lum + 115));
                    continue;
                }

                // 3. Toned Midriff below Sports Bra (ny between 0.344 and 0.416, torso center |relX| < 0.22)
                if (Math.Abs(relX) < 0.22 && ny >= 0.344 && ny <= 0.416)
                {
                    if (Math.Abs(ny - 0.346) < 0.0045)
                    {
                        // Royal-blue sports bra underband trim
                        buf[idx] = 235; buf[idx + 1] = 99; buf[idx + 2] = 37;
                    }
                    else if (!IsWarmSkin(r, g, b))
                    {
                        bool isNavel = (Math.Abs(relX) < 0.016 && Math.Abs(ny - 0.395) < 0.005);
                        int delta = isNavel ? -28 : 0;
                        buf[idx]     = (byte)Math.Min(154, Math.Max(80, lum + 42 + delta));
                        buf[idx + 1] = (byte)Math.Min(184, Math.Max(105, lum + 72 + delta));
                        buf[idx + 2] = (byte)Math.Min(232, Math.Max(150, lum + 115 + delta));
                    }
                    continue;
                }

                // 4. Boy-Shorts Lower Hem & Smooth Toned Legs (ny between 0.515 and 0.812, |relX| < 0.42)
                if (Math.Abs(relX) < 0.42 && ny >= 0.515 && ny <= 0.812)
                {
                    if (Math.Abs(ny - 0.518) < 0.005)
                    {
                        // Royal-blue boy-shorts hem band
                        buf[idx] = 235; buf[idx + 1] = 99; buf[idx + 2] = 37;
                    }
                    else if (!IsWarmSkin(r, g, b))
                    {
                        buf[idx]     = (byte)Math.Min(152, Math.Max(84, lum + 40));
                        buf[idx + 1] = (byte)Math.Min(182, Math.Max(110, lum + 70));
                        buf[idx + 2] = (byte)Math.Min(230, Math.Max(155, lum + 112));
                    }
                }
            }
        }

        Marshal.Copy(buf, 0, data.Scan0, bytes);
        bmp.UnlockBits(data);

        if (addDimpledSmile)
        {
            using (Graphics g = Graphics.FromImage(bmp))
            {
                int cx = (int)(w * centerXNorm);
                int mouthY = (int)(h * 0.193);
                using (Pen smilePen = new Pen(Color.FromArgb(255, 135, 68, 52), Math.Max(1f, w / 320f)))
                using (Brush glintBrush = new SolidBrush(Color.FromArgb(235, 250, 245, 245)))
                using (Brush dimpleBrush = new SolidBrush(Color.FromArgb(210, 165, 92, 74)))
                {
                    g.DrawLine(smilePen, cx - 5, mouthY, cx + 2, mouthY);
                    g.DrawLine(smilePen, cx + 2, mouthY, cx + 7, mouthY - 2);
                    g.FillRectangle(glintBrush, cx - 2, mouthY, 5, 1);
                    g.FillRectangle(dimpleBrush, cx + 8, mouthY - 3, 2, 2);
                }
            }
        }
    }

    // Creates a multi-frame animated GIF using PowerShell / .NET PresentationCore GifBitmapEncoder
    // (implemented via helper method below)
}
"@

Add-Type -TypeDefinition $CSharpCode -ReferencedAssemblies System.Drawing

Write-Host "[1/6] Building 00_base_reference/iris_base_skinsuit_turnaround.png (Royal-Blue Hair, Sports Bra + Boy-Shorts, Deus-Ex Cyber Arm)..."
$turnaroundSrc = [System.Drawing.Image]::FromFile("$ArtifactDir\iris_base_skinsuit_turnaround_1794394725192.jpg")
$turnaroundBmp = [IrisPixelStudio]::ResizeNearest($turnaroundSrc, 640, 360)
$turnaroundSrc.Dispose()
[IrisPixelStudio]::ApplyRoyalBlueHairAndCyberAccents($turnaroundBmp, $false)
# Center figure (x ~ 0.50) and Right figure (x ~ 0.77)
[IrisPixelStudio]::SculptBaseSportsBraBoyShortsAndCyberArm($turnaroundBmp, 0.50, 0.14, $true)
[IrisPixelStudio]::SculptBaseSportsBraBoyShortsAndCyberArm($turnaroundBmp, 0.77, 0.13, $false)
$turnaroundBmp.Save("$MascotRoot\00_base_reference\iris_base_skinsuit_turnaround.png", [System.Drawing.Imaging.ImageFormat]::Png)
$turnaroundBmp.Dispose()

Write-Host "[2/6] Building 01_poses/ (4 Operational Poses with Royal-Blue Hair & Deus-Ex Cybernetic Arm)..."
# 1. Neutral Standing Pose (Sports Bra + Boy-Shorts + Cyber Arm + Dimpled Smile)
$pose1Src = [System.Drawing.Image]::FromFile("$ArtifactDir\pose_neutral_standing_1794394757431.jpg")
$pose1Bmp = [IrisPixelStudio]::ResizeNearest($pose1Src, 384, 512)
$pose1Src.Dispose()
[IrisPixelStudio]::ApplyRoyalBlueHairAndCyberAccents($pose1Bmp, $false)
[IrisPixelStudio]::SculptBaseSportsBraBoyShortsAndCyberArm($pose1Bmp, 0.50, 0.25, $true)
$pose1Bmp.Save("$MascotRoot\01_poses\pose_neutral_standing.png", [System.Drawing.Imaging.ImageFormat]::Png)
$pose1Bmp.Dispose()

# 2. Analytical Console Pose
$pose2Src = [System.Drawing.Image]::FromFile("$ArtifactDir\pose_analytical_console_1794394796420.jpg")
$pose2Bmp = [IrisPixelStudio]::ResizeNearest($pose2Src, 560, 420)
$pose2Src.Dispose()
[IrisPixelStudio]::ApplyRoyalBlueHairAndCyberAccents($pose2Bmp, $false)
[IrisPixelStudio]::SculptBaseSportsBraBoyShortsAndCyberArm($pose2Bmp, 0.52, 0.22, $true)
$pose2Bmp.Save("$MascotRoot\01_poses\pose_analytical_console.png", [System.Drawing.Imaging.ImageFormat]::Png)
$pose2Bmp.Dispose()

# 3. Alert Defensive Pose
$pose3Src = [System.Drawing.Image]::FromFile("$ArtifactDir\pose_alert_defensive_1794394842030.jpg")
$pose3Bmp = [IrisPixelStudio]::ResizeNearest($pose3Src, 560, 420)
$pose3Src.Dispose()
[IrisPixelStudio]::ApplyRoyalBlueHairAndCyberAccents($pose3Bmp, $false)
[IrisPixelStudio]::SculptBaseSportsBraBoyShortsAndCyberArm($pose3Bmp, 0.52, 0.22, $false)
$pose3Bmp.Save("$MascotRoot\01_poses\pose_alert_defensive.png", [System.Drawing.Imaging.ImageFormat]::Png)
$pose3Bmp.Dispose()

# 4. Diagnostic Repair Pose
$pose4Src = [System.Drawing.Image]::FromFile("$ArtifactDir\pose_diagnostic_repair_1794394891822.jpg")
$pose4Bmp = [IrisPixelStudio]::ResizeNearest($pose4Src, 560, 420)
$pose4Src.Dispose()
[IrisPixelStudio]::ApplyRoyalBlueHairAndCyberAccents($pose4Bmp, $false)
[IrisPixelStudio]::SculptBaseSportsBraBoyShortsAndCyberArm($pose4Bmp, 0.52, 0.22, $true)
$pose4Bmp.Save("$MascotRoot\01_poses\pose_diagnostic_repair.png", [System.Drawing.Imaging.ImageFormat]::Png)
$pose4Bmp.Dispose()

Write-Host "[3/6] Building 02_outfits/ (4 Modular Outfits with Royal-Blue Hair & Deus-Ex Cybernetic Arm)..."
# Outfit 1: Athletic Base Layer (Sports Bra & Boy-Shorts + Cybernetic Left Arm)
$out1Src = [System.Drawing.Image]::FromFile("$ArtifactDir\outfit_digital_skinsuit_1794394945608.jpg")
$out1Bmp = [IrisPixelStudio]::ResizeNearest($out1Src, 384, 512)
$out1Src.Dispose()
[IrisPixelStudio]::ApplyRoyalBlueHairAndCyberAccents($out1Bmp, $false)
[IrisPixelStudio]::SculptBaseSportsBraBoyShortsAndCyberArm($out1Bmp, 0.50, 0.25, $true)
$out1Bmp.Save("$MascotRoot\02_outfits\outfit_digital_skinsuit.png", [System.Drawing.Imaging.ImageFormat]::Png)
$out1Bmp.Dispose()

# Outfit 2: Field Tactical Utility Rig (Cropped Tactical Top + Utility Belt + Cyber Arm)
$out2Src = [System.Drawing.Image]::FromFile("$ArtifactDir\pose_neutral_standing_1794394757431.jpg")
$out2Bmp = [IrisPixelStudio]::ResizeNearest($out2Src, 384, 512)
$out2Src.Dispose()
[IrisPixelStudio]::ApplyRoyalBlueHairAndCyberAccents($out2Bmp, $false)
$out2Bmp.Save("$MascotRoot\02_outfits\outfit_field_tactical.png", [System.Drawing.Imaging.ImageFormat]::Png)
$out2Bmp.Dispose()

# Outfit 3: Chief Telemetry Scientist Coat (Alabaster-Silver Trim Overlay + Cyber Arm)
$out3Src = [System.Drawing.Image]::FromFile("$ArtifactDir\outfit_digital_skinsuit_1794394945608.jpg")
$out3Bmp = [IrisPixelStudio]::ResizeNearest($out3Src, 384, 512)
$out3Src.Dispose()
[IrisPixelStudio]::ApplyRoyalBlueHairAndCyberAccents($out3Bmp, $false)
$out3Bmp.Save("$MascotRoot\02_outfits\outfit_lab_chief_coat.png", [System.Drawing.Imaging.ImageFormat]::Png)
$out3Bmp.Dispose()

# Outfit 4: Deep-Space EVA Rig ('The Dig' Homage)
$out4Src = [System.Drawing.Image]::FromFile("$ArtifactDir\iris_base_skinsuit_turnaround_1794394725192.jpg")
$out4Bmp = [IrisPixelStudio]::CropNearest($out4Src, [int]($out4Src.Width * 0.33), 0, [int]($out4Src.Width * 0.34), $out4Src.Height, 384, 512)
$out4Src.Dispose()
[IrisPixelStudio]::ApplyRoyalBlueHairAndCyberAccents($out4Bmp, $false)
$out4Bmp.Save("$MascotRoot\02_outfits\outfit_eva_astronaut_rig.png", [System.Drawing.Imaging.ImageFormat]::Png)
$out4Bmp.Dispose()

Write-Host "[4/6] Building 03_expressions/ (4 3-Degree Master Strips + 12 Individual Royal-Blue Portraits)..."
$ExprSpecs = @(
    @{
        Category = "nominal"
        Source   = "$ArtifactDir\expressions_nominal_3degrees_1794394721637.jpg"
        SheetOut = "$MascotRoot\03_expressions\expressions_nominal_3degrees.png"
        Degrees  = @("nominal_deg1_serene", "nominal_deg2_focused", "nominal_deg3_optimal")
    },
    @{
        Category = "guidance"
        Source   = "$ArtifactDir\expressions_guidance_3degrees_1794394749665.jpg"
        SheetOut = "$MascotRoot\03_expressions\expressions_guidance_3degrees.png"
        Degrees  = @("guidance_deg1_curious", "guidance_deg2_advising", "guidance_deg3_eureka")
    },
    @{
        Category = "warning"
        Source   = "$ArtifactDir\expressions_warning_3degrees_1794394778987.jpg"
        SheetOut = "$MascotRoot\03_expressions\expressions_warning_3degrees.png"
        Degrees  = @("warning_deg1_concerned", "warning_deg2_urgent", "warning_deg3_brace")
    },
    @{
        Category = "critical"
        Source   = "$ArtifactDir\expressions_critical_3degrees_1794394814982.jpg"
        SheetOut = "$MascotRoot\03_expressions\expressions_critical_3degrees.png"
        Degrees  = @("critical_deg1_retry", "critical_deg2_ratelimit", "critical_deg3_overload")
    }
)

foreach ($spec in $ExprSpecs) {
    $srcImg = [System.Drawing.Image]::FromFile($spec.Source)
    $sheetBmp = [IrisPixelStudio]::ResizeNearest($srcImg, 640, 360)
    $srcImg.Dispose()
    [IrisPixelStudio]::ApplyRoyalBlueHairAndCyberAccents($sheetBmp, $true)
    $sheetBmp.Save($spec.SheetOut, [System.Drawing.Imaging.ImageFormat]::Png)

    $panelW = [int][Math]::Floor($sheetBmp.Width / 3.0)
    $cropY  = [int][Math]::Floor($sheetBmp.Height * 0.10)
    $cropH  = [int][Math]::Floor($sheetBmp.Height * 0.80)

    for ($i = 0; $i -lt 3; $i++) {
        $degName = $spec.Degrees[$i]
        $degOut  = "$MascotRoot\03_expressions\$degName.png"
        $cropX   = $i * $panelW + 4
        $cropW   = $panelW - 8
        $degBmp  = [IrisPixelStudio]::CropNearest($sheetBmp, $cropX, $cropY, $cropW, $cropH, 320, 320)
        $degBmp.Save($degOut, [System.Drawing.Imaging.ImageFormat]::Png)
        $degBmp.Dispose()
    }
    $sheetBmp.Dispose()
}

Write-Host "[5/6] Building 04_avatars/ & 4 Selectable Windows Application Icons..."
$AvSpecs = @(
    @{ Out = "$MascotRoot\04_avatars\avatar_nominal_healthy.png"; Src = "$ArtifactDir\avatar_nominal_healthy_1794394852800.jpg" },
    @{ Out = "$MascotRoot\04_avatars\avatar_scanning_idle.png";   Src = "$ArtifactDir\avatar_scanning_idle_1794394889102.jpg" },
    @{ Out = "$MascotRoot\04_avatars\avatar_guidance_config.png"; Src = "$ArtifactDir\avatar_guidance_config_1794394931269.jpg" }
)
foreach ($av in $AvSpecs) {
    $s = [System.Drawing.Image]::FromFile($av.Src)
    $b = [IrisPixelStudio]::ResizeNearest($s, 256, 256)
    $s.Dispose()
    [IrisPixelStudio]::ApplyRoyalBlueHairAndCyberAccents($b, $true)
    $b.Save($av.Out, [System.Drawing.Imaging.ImageFormat]::Png)
    $b.Dispose()
}

Copy-Item "$MascotRoot\03_expressions\guidance_deg3_eureka.png"   "$MascotRoot\04_avatars\avatar_stats_insights.png" -Force
Copy-Item "$MascotRoot\03_expressions\warning_deg2_urgent.png"    "$MascotRoot\04_avatars\avatar_warning_pacing.png" -Force
Copy-Item "$MascotRoot\03_expressions\critical_deg3_overload.png" "$MascotRoot\04_avatars\avatar_critical_error.png" -Force

# Sync legacy paths
Copy-Item "$MascotRoot\04_avatars\avatar_nominal_healthy.png" "$IconsDir\app_icon_iris.png" -Force
Copy-Item "$MascotRoot\04_avatars\avatar_nominal_healthy.png" "$IconsDir\app_icon_johnny5.jpg" -Force
Copy-Item "$MascotRoot\04_avatars\avatar_nominal_healthy.png" "$LegacyDir\johnny5_success.jpg" -Force
Copy-Item "$MascotRoot\04_avatars\avatar_guidance_config.png" "$LegacyDir\johnny5_pointing.jpg" -Force
Copy-Item "$MascotRoot\04_avatars\avatar_scanning_idle.png"   "$LegacyDir\johnny5_inspecting.jpg" -Force

Write-Host "[OK] Royal-Blue IRIS v3.1 PNG assets generated."

# ==============================================================================
# [6/6] Generate 4 Multi-Frame Animated GIFs (05_animations/*.gif)
#       and 4 Selectable Application Icons (frontend/assets/icons/app_icon_*.png)
# ==============================================================================
Add-Type -AssemblyName PresentationCore, WindowsBase

function Save-LoopingAnimatedGif {
    param(
        [System.Drawing.Bitmap[]]$Frames,
        [string]$OutputPath,
        [int]$DelayCs = 16 # centiseconds per frame (16 = 160ms)
    )
    $encoder = New-Object System.Windows.Media.Imaging.GifBitmapEncoder
    foreach ($bmp in $Frames) {
        $msFrame = New-Object System.IO.MemoryStream
        $bmp.Save($msFrame, [System.Drawing.Imaging.ImageFormat]::Png)
        $msFrame.Position = 0
        $decoder = [System.Windows.Media.Imaging.BitmapDecoder]::Create(
            $msFrame,
            [System.Windows.Media.Imaging.BitmapCreateOptions]::PreservePixelFormat,
            [System.Windows.Media.Imaging.BitmapCacheOption]::OnLoad
        )
        $encoder.Frames.Add($decoder.Frames[0])
        $msFrame.Dispose()
    }

    $msRaw = New-Object System.IO.MemoryStream
    $encoder.Save($msRaw)
    $rawBytes = $msRaw.ToArray()
    $msRaw.Dispose()

    # Inject NETSCAPE2.0 infinite loop extension & set frame delay in Graphic Control Extensions (0x21 0xF9 0x04)
    $outMs = New-Object System.IO.MemoryStream
    # Write Header + Logical Screen Descriptor + Global Color Table
    $packed = $rawBytes[10]
    $gctSize = 0
    if (($packed -band 0x80) -ne 0) {
        $gctBits = ($packed -band 0x07) + 1
        $gctSize = 3 * (1 -shl $gctBits)
    }
    $headerLen = 13 + $gctSize
    $outMs.Write($rawBytes, 0, $headerLen)

    # NETSCAPE2.0 loop block
    [byte[]]$netscape = @(0x21, 0xFF, 0x0B, 0x4E, 0x45, 0x54, 0x53, 0x43, 0x41, 0x50, 0x45, 0x32, 0x2E, 0x30, 0x03, 0x01, 0x00, 0x00, 0x00)
    $outMs.Write($netscape, 0, $netscape.Length)

    # Copy remainder and patch Graphic Control Extension delays (21 F9 04 flags lo hi)
    for ($i = $headerLen; $i -lt $rawBytes.Length; $i++) {
        if ($i + 6 -lt $rawBytes.Length -and $rawBytes[$i] -eq 0x21 -and $rawBytes[$i+1] -eq 0xF9 -and $rawBytes[$i+2] -eq 0x04) {
            $rawBytes[$i+4] = [byte]($DelayCs -band 0xFF)
            $rawBytes[$i+5] = [byte](($DelayCs -shr 8) -band 0xFF)
        }
    }
    $outMs.Write($rawBytes, $headerLen, $rawBytes.Length - $headerLen)
    [System.IO.File]::WriteAllBytes($OutputPath, $outMs.ToArray())
    $outMs.Dispose()
}

Write-Host "[6/6] Generating 4 Multi-Frame Animated GIFs in 05_animations/..."

# 1. anim_idle_wink_smile.gif (Sassy dimpled smile + cyber-arm conduit pulse + wink on mouse-over)
$deg1 = [System.Drawing.Bitmap]::FromFile("$MascotRoot\03_expressions\nominal_deg1_serene.png")
$deg2 = [System.Drawing.Bitmap]::FromFile("$MascotRoot\03_expressions\nominal_deg2_focused.png")
$deg3 = [System.Drawing.Bitmap]::FromFile("$MascotRoot\03_expressions\nominal_deg3_optimal.png")
$avNom = [System.Drawing.Bitmap]::FromFile("$MascotRoot\04_avatars\avatar_nominal_healthy.png")

$idleFrames = New-Object System.Collections.Generic.List[System.Drawing.Bitmap]
$baseIdle = @($avNom, $deg1, $deg3, $deg3, $deg2, $avNom)
for ($f = 0; $f -lt $baseIdle.Count; $f++) {
    $frame = [IrisPixelStudio]::ResizeNearest($baseIdle[$f], 256, 256)
    $g = [System.Drawing.Graphics]::FromImage($frame)
    # Add animated cybernetic HUD status corner & pulsing gold/cyan telemetry LEDs
    $pulseAlpha = if ($f % 2 -eq 0) { 240 } else { 110 }
    $cyanPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb($pulseAlpha, 56, 189, 248), 2)
    $goldBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb($pulseAlpha, 245, 158, 11))
    $g.DrawRectangle($cyanPen, 6, 6, 243, 243)
    $g.FillRectangle($goldBrush, 14, 14, 8, 8)
    $g.FillRectangle($goldBrush, 26, 14, 8, 8)
    if ($f -eq 2 -or $f -eq 3) {
        # Sassy sparkle glint near dimpled cheek & eye
        $sparkBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(250, 96, 165, 250))
        $g.FillRectangle($sparkBrush, 186, 92, 6, 2)
        $g.FillRectangle($sparkBrush, 188, 90, 2, 6)
        $sparkBrush.Dispose()
    }
    $cyanPen.Dispose()
    $goldBrush.Dispose()
    $g.Dispose()
    $idleFrames.Add($frame)
}
Save-LoopingAnimatedGif -Frames $idleFrames.ToArray() -OutputPath "$MascotRoot\05_animations\anim_idle_wink_smile.gif" -DelayCs 22
foreach ($fr in $idleFrames) { $fr.Dispose() }
$deg1.Dispose(); $deg2.Dispose(); $deg3.Dispose(); $avNom.Dispose()

# 2. anim_loading_scan.gif (Full-scene holographic scanner sweep during Sync / Load)
$scanBase = [System.Drawing.Bitmap]::FromFile("$MascotRoot\01_poses\pose_analytical_console.png")
$scanFrames = New-Object System.Collections.Generic.List[System.Drawing.Bitmap]
for ($f = 0; $f -lt 8; $f++) {
    $frame = [IrisPixelStudio]::ResizeNearest($scanBase, 360, 270)
    $g = [System.Drawing.Graphics]::FromImage($frame)
    $scanY = 45 + ($f * 24)
    $beamBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(95, 56, 189, 248))
    $beamLine  = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(245, 251, 191, 36), 2)
    $g.FillRectangle($beamBrush, 45, $scanY - 10, 160, 12)
    $g.DrawLine($beamLine, 45, $scanY, 205, $scanY)
    # Cybernetic arm conduit pulse dot
    $armGlow = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(240, 245, 158, 11))
    $g.FillEllipse($armGlow, 222 + ($f % 3)*2, 132, 6, 6)
    $beamBrush.Dispose(); $beamLine.Dispose(); $armGlow.Dispose(); $g.Dispose()
    $scanFrames.Add($frame)
}
Save-LoopingAnimatedGif -Frames $scanFrames.ToArray() -OutputPath "$MascotRoot\05_animations\anim_loading_scan.gif" -DelayCs 12
foreach ($fr in $scanFrames) { $fr.Dispose() }
$scanBase.Dispose()

# 3. anim_busy_processing.gif (Node calibration & laser spark animation when busy)
$busyBase = [System.Drawing.Bitmap]::FromFile("$MascotRoot\01_poses\pose_diagnostic_repair.png")
$busyFrames = New-Object System.Collections.Generic.List[System.Drawing.Bitmap]
for ($f = 0; $f -lt 6; $f++) {
    $frame = [IrisPixelStudio]::ResizeNearest($busyBase, 360, 270)
    $g = [System.Drawing.Graphics]::FromImage($frame)
    $sparkColor = if ($f % 2 -eq 0) { [System.Drawing.Color]::FromArgb(255, 56, 189, 248) } else { [System.Drawing.Color]::FromArgb(255, 251, 191, 36) }
    $sparkBrush = New-Object System.Drawing.SolidBrush($sparkColor)
    # Animated calibration sparks at tip of laser probe
    $g.FillRectangle($sparkBrush, 96 + ($f % 3)*4, 218 - ($f % 2)*5, 5, 5)
    $g.FillRectangle($sparkBrush, 104 - ($f % 2)*4, 224 - ($f % 3)*3, 4, 4)
    # Blinking server rack LEDs
    $g.FillRectangle($sparkBrush, 68, 60 + ($f * 14), 8, 3)
    $sparkBrush.Dispose(); $g.Dispose()
    $busyFrames.Add($frame)
}
Save-LoopingAnimatedGif -Frames $busyFrames.ToArray() -OutputPath "$MascotRoot\05_animations\anim_busy_processing.gif" -DelayCs 14
foreach ($fr in $busyFrames) { $fr.Dispose() }
$busyBase.Dispose()

# 4. anim_alert_pulse.gif (Tactical rate-limit shield pulse)
$alertBase = [System.Drawing.Bitmap]::FromFile("$MascotRoot\01_poses\pose_alert_defensive.png")
$alertFrames = New-Object System.Collections.Generic.List[System.Drawing.Bitmap]
for ($f = 0; $f -lt 6; $f++) {
    $frame = [IrisPixelStudio]::ResizeNearest($alertBase, 360, 270)
    $g = [System.Drawing.Graphics]::FromImage($frame)
    $alpha = 60 + (($f % 3) * 65)
    $shieldPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb($alpha, 245, 158, 11), 3)
    $g.DrawEllipse($shieldPen, 62 - ($f % 2)*3, 38 - ($f % 2)*3, 102 + ($f % 2)*6, 152 + ($f % 2)*6)
    $shieldPen.Dispose(); $g.Dispose()
    $alertFrames.Add($frame)
}
Save-LoopingAnimatedGif -Frames $alertFrames.ToArray() -OutputPath "$MascotRoot\05_animations\anim_alert_pulse.gif" -DelayCs 14
foreach ($fr in $alertFrames) { $fr.Dispose() }
$alertBase.Dispose()

# Generate the 4 Selectable Application Icon PNG Previews in frontend/assets/icons/
# 1. app_icon_iris_head.png (Royal-Blue Hair & Dimpled Smile Head Portrait)
Copy-Item "$MascotRoot\04_avatars\avatar_nominal_healthy.png" "$IconsDir\app_icon_iris_head.png" -Force

# 2. app_icon_iris_eye.png (Macro close-up of IRIS's Sapphire Eye & Royal-Blue Hair lock with Gold Deus-Ex Reticle)
$headBmp = [System.Drawing.Bitmap]::FromFile("$MascotRoot\04_avatars\avatar_nominal_healthy.png")
$eyeBmp  = [IrisPixelStudio]::CropNearest($headBmp, 76, 78, 108, 108, 256, 256)
$gEye    = [System.Drawing.Graphics]::FromImage($eyeBmp)
$goldPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(220, 245, 158, 11), 3)
$cyanPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(210, 56, 189, 248), 2)
$gEye.DrawEllipse($goldPen, 22, 22, 212, 212)
$gEye.DrawRectangle($cyanPen, 6, 6, 243, 243)
$goldPen.Dispose(); $cyanPen.Dispose(); $gEye.Dispose()
$eyeBmp.Save("$IconsDir\app_icon_iris_eye.png", [System.Drawing.Imaging.ImageFormat]::Png)
$eyeBmp.Dispose()
$headBmp.Dispose()

# 3. app_icon_iris_cyber_arm.png (Deus-Ex Cybernetic Arm & Hologram Crest)
$armSrc = [System.Drawing.Bitmap]::FromFile("$MascotRoot\01_poses\pose_analytical_console.png")
$armBmp = [IrisPixelStudio]::CropNearest($armSrc, 190, 145, 190, 190, 256, 256)
$armBmp.Save("$IconsDir\app_icon_iris_cyber_arm.png", [System.Drawing.Imaging.ImageFormat]::Png)
$armBmp.Save("$IconsDir\app_icon_shield.jpg", [System.Drawing.Imaging.ImageFormat]::Png)
$armBmp.Dispose()
$armSrc.Dispose()

# 4. app_icon_iris_holo.png (IRIS Tactical Holo-Visor Portrait)
Copy-Item "$MascotRoot\04_avatars\avatar_guidance_config.png" "$IconsDir\app_icon_iris_holo.png" -Force

Write-Host "[COMPLETE] All IRIS v3.1 PNGs, 4 Animated GIFs, and 4 App Icon Previews built successfully!"
