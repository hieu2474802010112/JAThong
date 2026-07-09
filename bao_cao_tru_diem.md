# BÁO CÁO HỆ THỐNG CHẤM ĐIỂM CV
### Dự án: JAThong Backend — CV Evaluation Engine
**Tài liệu tham chiếu:** [`scorer.py`](file:///d:/Backend-JAThong/app/services/ai/scorer.py)
**Thang điểm:** 10.0 | **Điểm sàn:** 5.5 – 6.0 | **Điểm tối đa:** 10.0

---

## 1. TỔNG QUAN QUY TRÌNH

Hệ thống chấm điểm CV áp dụng mô hình **Hybrid Scoring** gồm 2 tầng:

| Tầng | Mô tả |
|------|-------|
| **Tầng 1 – AI (Gemini)** | Chấm điểm thô theo rubric động, trả về `CVEvaluationResult` |
| **Tầng 2 – Python (scorer.py)** | Áp dụng business rules, floor guards, caps và bonus lên kết quả AI |

```
Bắt đầu: 10.0 điểm
    ↓ Trừ: Format Deductions (STEP 2)
    ↓ Trừ/Cộng: Quality Adjustments (STEP 3)
    ↓ Tính: Final Score Calculation + Weakness Caps (STEP 4)
    ↓ Python: Floor Guards + Bonus cứng
Kết quả cuối: round(max(floor, min(10.0, final)), 1)
```

---

## 2. BẢNG TRỪ ĐIỂM CHI TIẾT

### 2.1 — FORMAT DEDUCTIONS (Trừ điểm hình thức)

> [!NOTE]
> Áp dụng ở **STEP 2** trong prompt Gemini. Các mức deduction này cố định, AI không được tự ý thay đổi.

#### 📐 Bố cục & Trình bày

| Lỗi | Mức trừ |
|-----|---------|
| Layout lộn xộn, thiếu phân cấp heading | **−0.2 đến −0.3** |
| *Layout ATS-friendly (đen trắng đơn giản)* | *Không trừ* |

---

#### 🎯 Mục tiêu nghề nghiệp / Profile Summary

| Trường hợp | Mức trừ |
|------------|---------|
| Hoàn toàn thiếu **HOẶC** không rõ hướng | **−1.0** |
| Gộp mục tiêu ngắn hạn/dài hạn, thiếu nhỏ | **−0.2 đến −0.3** |

> [!IMPORTANT]
> **CAREER OBJECTIVE MITIGATION RULE:** Nếu mục tiêu bị thiếu hoàn toàn → Python override điểm component về **9.5** (chỉ trừ thực tế **−0.5**) và **KHÔNG** cho phép mục này kéo Weakness Caps hoặc hạn chế điểm cuối.

---

#### 📅 Ngày tháng Kinh nghiệm làm việc

| Lỗi | Mức trừ |
|-----|---------|
| Thiếu tháng trong ngày bắt đầu/kết thúc (VD: chỉ ghi "2024", "2024 - Nay") | **−1.0 / mỗi mục** |
| Có đủ tháng+năm (VD: "10/2023 - 02/2024") | *Không trừ* |

---

#### 🛠️ Kỹ năng

| Lỗi | Mức trừ |
|-----|---------|
| Dùng rating chủ quan: thanh tiến trình, sao, %, bar chart | **−0.3 đến −0.5** |
| Liệt kê tên kỹ năng không có rating | *Không trừ* |

> [!NOTE]
> Đây là lỗi **hình thức/thẩm mỹ**, trọng số thấp hơn so với thiếu dữ liệu kinh nghiệm thực tế.

---

#### 🔗 Portfolio / Liên kết

| Ngành | Trường hợp | Mức trừ |
|-------|------------|---------|
| **IT, Marketing, Creative, Art/Design, Media** | Thiếu portfolio | **−1.0** |
| **Kế toán, HR, Sales, Admin, Logistics, Supply Chain** | Thiếu portfolio | **0 (Miễn trừ)** |
| **Ngành khác** | Thiếu portfolio | **−0.2 đến −0.3** |

##### Social Spam Rule

| Ngành | Điều kiện | Mức trừ |
|-------|-----------|---------|
| **Tech / Dev / Data / IT** | Có Facebook/Instagram/TikTok mà **không có** GitHub/GitLab/Kaggle | **−1.0** |
| **Sales / HR / Tuyển dụng** | Có Facebook/TikTok → coi là personal branding | **0 (Chấp nhận)** |
| Ngành khác | Mạng xã hội cá nhân | Trừ nhỏ (minor) |

---

#### 📧 Thông tin liên hệ

| Lỗi | Mức trừ |
|-----|---------|
| Thiếu Email **hoặc** Số điện thoại | **−0.5** |
| Email không chuyên nghiệp (cute, baby, sexy, boy, girl…) | **−0.5** |

---

### 2.2 — QUALITY ADJUSTMENTS (STEP 3)

| Tiêu chí | Mức |
|----------|-----|
| Bullet point sơ sài, không có KPI hoặc kết quả định lượng | **−tối đa 1.0** |
| Thành tích nổi bật, giải thưởng, công trình nghiên cứu | **+tối đa 1.0** |

---

### 2.3 — WEAKNESS CAPS (STEP 4 — Giới hạn điểm theo số điểm yếu nội dung)

> [!IMPORTANT]
> Chỉ đếm các điểm yếu về **chất lượng nội dung** — **KHÔNG** tính các lỗi format nhỏ sau:
> - Thiếu mục tiêu nghề nghiệp
> - Thiếu portfolio / link mạng xã hội
> - Rating kỹ năng dạng bar
> - Bố cục, font, màu sắc, layout
> - Thiếu tháng/năm trong ngày tháng

| Số điểm yếu nội dung | Điểm tối đa được phép |
|--------------------|----------------------|
| **1 – 2** điểm yếu | ≤ **9.6** |
| **3 – 4** điểm yếu | ≤ **8.8** |
| **≥ 5** điểm yếu lớn | ≤ **7.0** |

---

## 3. BONUS CỨng (Python-side — STEP 7)

| Điều kiện phát hiện trong raw text CV | Điểm cộng |
|---------------------------------------|-----------|
| Có **cả** bài báo khoa học **VÀ** giải thi đấu lớn | **+1.0** |
| Chỉ có **một trong hai** | **+0.7** |

**Từ khóa phát hiện bài báo:** `publi`, `paper`, `research`, `bài báo`, `nghiên cứu`, `olympiad`, `kinh tế lượng`

**Từ khóa phát hiện giải thưởng:** `champion`, `runner`, `winner`, `prize`, `quán quân`, `á quân`, `giải`, `contest`, `leadership`, `finalist`, `doanh nhân tập sự`

---

## 4. FLOOR GUARDS (Python-side — Điểm sàn bảo vệ)

### 4.1 — Component-level Floors

| Tiêu chí component | Điểm sàn tối thiểu |
|--------------------|-------------------|
| Layout / chính tả / font / bố cục | **8.0** |
| Portfolio (ngành không phải creative) | **8.0** |
| Portfolio (ngành được miễn: Kế toán, HR, Sales…) | **10.0 (cố định)** |
| Rating kỹ năng dạng bar | **8.0** |
| Mục tiêu ngắn/dài hạn (khi obj_score ≥ 7.0) | **≥ obj_score − 0.3** |

### 4.2 — Final Score Floor

| Điều kiện | Điểm sàn cuối |
|-----------|---------------|
| Mặc định | **5.5** |
| Kinh nghiệm ≥ 8.5 **VÀ** Kỹ năng cứng ≥ 8.5 | **6.0** |

### 4.3 — ATS Exemption (Tech)

> Điểm Hoạt động ngoại khóa ≤ 1.0 của ứng viên Tech → **bỏ qua**, không đưa vào tính điểm trung bình.

---

## 5. CÔNG THỨC TÍNH ĐIỂM CUỐI

```
base_score = trung_bình(valid_component_scores)   # sau khi áp floor guards

final_score = base_score
→ Áp Weakness Caps (nếu n ≥ 1)
→ Cộng Flat Bonus (nếu có publication/giải thưởng)

kết_quả = round(max(floor_score, min(10.0, final_score)), 1)
```

---

## 6. PHÂN LOẠI NGÀNH (Industry Detection)

| Nhóm | Từ khóa nhận diện |
|------|-------------------|
| **Tech / IT** | công nghệ, kỹ thuật, it, developer, software, data, system, lập trình, mạng, computer, dev, tech, analyst |
| **Creative / Marketing** | marketing, creative, design, thiết kế, art, media, truyền thông, content, sáng tạo, mkt |
| **Portfolio Exempt** | kế toán, accounting, hr, nhân sự, human resource, sales, kinh doanh, admin, hành chính, logistics, vận tải, chuỗi cung ứng, supply chain |
| **Social Branding OK** | sales, kinh doanh, hr, nhân sự, human resource, tuyển dụng, recruitment |

---

*Nguồn: [`scorer.py`](file:///d:/Backend-JAThong/app/services/ai/scorer.py) — hàm `calculate_final_score()` và hằng số `get_dynamic_criteria()`*
