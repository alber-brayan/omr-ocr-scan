package com.lectoraomr.camera.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.lectoraomr.camera.ui.theme.Mute

object Credits {
    const val INITIALS = "A.B.M.R"
    const val YEAR = "2026"
    const val RIGHTS = "Licencia MIT"
    const val LINE = "© $YEAR $INITIALS  ·  $RIGHTS"
    const val PRIVATE = "Alberto Brayan · OMR OCR SCAN"
}

@Composable
fun CreditsFooter(modifier: Modifier = Modifier) {
    Column(
        modifier
            .fillMaxWidth()
            .padding(top = 20.dp, bottom = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            "OCR OMR SCAN",
            color = Mute,
            fontSize = 11.sp,
            letterSpacing = 1.4.sp,
            textAlign = TextAlign.Center
        )
        Text(
            Credits.LINE,
            color = Mute.copy(alpha = 0.85f),
            fontSize = 10.sp,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 4.dp)
        )
        Text(
            Credits.PRIVATE,
            color = Mute.copy(alpha = 0.7f),
            fontSize = 10.sp,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 2.dp)
        )
    }
}
