"""Boxify — YOLO veri hazırlama ve model yaşam döngüsü atölyesi.

Kendi nesnelerin için (balon, araç, ürün, kusur… ne olursa) veri seti
hazırlamanın sekiz aracını tek çatı altında toplar: video kırpma, kare alma,
oto etiket, elle etiket, veri denetimi, hata analizi, model karşılaştırma ve
model export.

3.0.0: Model Karşılaştır aracı (aynı videoda 1-3 model, model başına sınıf ve
       çıkarım ayarı) + araç geçişlerindeki donmaların giderilmesi.
2.0.2: TR/EN arayüz dili desteği (boxify/dil.py eklentisi).
"""

SURUM = "3.0.0"
UYGULAMA_ADI = "Boxify"
