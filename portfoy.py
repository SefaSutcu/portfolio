import os
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
import requests
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import time
import logging

# Logging ayarları - encoding sorununu çöz
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Console encoding ayarı
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def portfoy_raporu():
    """Ana portföy raporu fonksiyonu"""
    
    # --- Veri ---
    data = {
        "altin": [
            {"banka": "Ziraat", "adet": 4.0, "alis_fiyati": 4206.564554},
            {"banka": "Yapıkredi", "adet": 1.0, "alis_fiyati": 2957.77},
        ],
        "hisseler": [
            {"kod": "AKBNK", "adet": 32, "alis_fiyati": 60.89},
            {"kod": "BIMAS", "adet": 2, "alis_fiyati": 554.6},
            {"kod": "TCELL", "adet": 20, "alis_fiyati": 84.70},
            {"kod": "SASA", "adet": 320, "alis_fiyati": 5.28},
            {"kod": "SISE", "adet": 20, "alis_fiyati": 46.42},
            {"kod": "DOAS", "adet": 4, "alis_fiyati": 268.48},
            {"kod": "MAVI", "adet": 40, "alis_fiyati": 47.06},
            {"kod": "AEFES", "adet": 50, "alis_fiyati": 24.79},
            {"kod": "AKCNS", "adet": 8, "alis_fiyati": 137.68},
            {"kod": "TAVHL", "adet": 3, "alis_fiyati": 241.0},
        ],
    }

    def banka_altin_kurlari_getir():
        """Banka altın kurlarını web scraping ile çeker"""
        urls = {
            "Ziraat": "https://altin.doviz.com/ziraat-bankasi/gram-altin",
            "Yapıkredi": "https://altin.doviz.com/yapikredi/gram-altin",
        }
        kurlar = {}
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        
        for banka, url in urls.items():
            try:
                logger.info(f"{banka} bankası altın fiyatı alınıyor...")
                response = requests.get(url, timeout=15, headers=headers)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, "html.parser")
                
                # Farklı selector'ları dene
                fiyat_elementi = (
                    soup.find("span", {"data-socket-attr": "bid"}) or
                    soup.find("span", {"class": "value"}) or
                    soup.find("div", {"class": "value"}) or
                    soup.find("span", string=lambda x: x and "," in str(x) and len(str(x)) > 4)
                )
                
                if not fiyat_elementi or not fiyat_elementi.text:
                    logger.warning(f"{banka} - Fiyat elementi bulunamadı, alternatif yöntem deneniyor...")
                    # Alternatif: sayısal değer içeren span'ları ara
                    spans = soup.find_all("span")
                    for span in spans:
                        text = span.get_text(strip=True)
                        if "," in text and len(text) > 4:
                            try:
                                # Test için dönüştürmeyi dene
                                test_fiyat = float(text.replace(".", "").replace(",", "."))
                                if 1000 < test_fiyat < 10000:  # Makul altın fiyat aralığı
                                    fiyat_elementi = span
                                    break
                            except:
                                continue
                
                if fiyat_elementi and fiyat_elementi.text:
                    fiyat_text = fiyat_elementi.text.strip()
                    # "2.345,67" formatını 2345.67'ye çevir
                    fiyat = float(fiyat_text.replace(".", "").replace(",", "."))
                    kurlar[banka] = fiyat
                    logger.info(f"{banka}: {fiyat} TL")
                else:
                    raise ValueError("Fiyat elementi bulunamadı veya boş")
                    
            except Exception as e:
                logger.error(f"{banka} altın fiyatı alınamadı: {e}")
                kurlar[banka] = None
                
            # Rate limiting için bekleme
            time.sleep(1)
        
        return kurlar

    def hisse_fiyatlarini_getir(kodlar):
        """Yahoo Finance'den hisse fiyatlarını çeker"""
        fiyatlar = {}
        
        for kod in kodlar:
            try:
                logger.info(f"{kod} hisse fiyatı alınıyor...")
                ticker = yf.Ticker(f"{kod}.IS")
                
                # Son 5 gün verisi al
                hist = ticker.history(period="5d", interval="1d")
                
                if not hist.empty and 'Close' in hist.columns:
                    son_fiyat = hist['Close'].dropna()
                    if not son_fiyat.empty:
                        fiyat = round(float(son_fiyat.iloc[-1]), 2)
                        fiyatlar[kod] = fiyat
                        logger.info(f"{kod}: {fiyat} TL")
                    else:
                        raise ValueError("Kapanış fiyatı verisi boş")
                else:
                    raise ValueError("Geçmiş veri boş")
                    
            except Exception as e:
                logger.error(f"{kod} hisse fiyatı alınamadı: {e}")
                fiyatlar[kod] = None
                
            # Rate limiting
            time.sleep(0.5)
        
        return fiyatlar

    def portfoy_df_olustur(data):
        """Portföy DataFrame'lerini oluşturur"""
        
        # Altın DataFrame
        altin_df = pd.DataFrame(data["altin"])
        altin_kurlar = banka_altin_kurlari_getir()
        
        altin_df["guncel_fiyat"] = altin_df["banka"].map(altin_kurlar)
        # Güncel fiyat alınamazsa alış fiyatını kullan
        altin_df["guncel_fiyat"] = altin_df["guncel_fiyat"].fillna(altin_df["alis_fiyati"])
        
        altin_df["toplam_alis"] = altin_df["adet"] * altin_df["alis_fiyati"]
        altin_df["toplam_guncel"] = altin_df["adet"] * altin_df["guncel_fiyat"]
        altin_df["kar_zarar"] = altin_df["toplam_guncel"] - altin_df["toplam_alis"]
        altin_df["yuzde"] = altin_df.apply(
            lambda row: (row["kar_zarar"] / row["toplam_alis"] * 100) if row["toplam_alis"] != 0 else 0.0,
            axis=1
        )

        # Hisse DataFrame
        hisse_df = pd.DataFrame(data["hisseler"])
        
        # Aynı hisse kodları varsa birleştir (ağırlıklı ortalama)
        if len(hisse_df) != len(hisse_df['kod'].unique()):
            logger.info("Tekrarlanan hisse kodları birleştiriliyor...")
            hisse_df = hisse_df.groupby("kod", as_index=False).agg({
                "adet": "sum", 
                "alis_fiyati": "mean"
            })
        
        hisse_fiyatlar = hisse_fiyatlarini_getir(hisse_df["kod"].tolist())
        
        hisse_df["guncel_fiyat"] = hisse_df["kod"].map(hisse_fiyatlar)
        # Güncel fiyat alınamazsa alış fiyatını kullan
        hisse_df["guncel_fiyat"] = hisse_df["guncel_fiyat"].fillna(hisse_df["alis_fiyati"])
        
        hisse_df["toplam_alis"] = hisse_df["adet"] * hisse_df["alis_fiyati"]
        hisse_df["toplam_guncel"] = hisse_df["adet"] * hisse_df["guncel_fiyat"]
        hisse_df["kar_zarar"] = hisse_df["toplam_guncel"] - hisse_df["toplam_alis"]
        hisse_df["yuzde"] = hisse_df.apply(
            lambda row: (row["kar_zarar"] / row["toplam_alis"] * 100) if row["toplam_alis"] != 0 else 0.0,
            axis=1
        )

        return altin_df, hisse_df

    def grafik_ciz(df, x_col, y_col1, y_col2, title, dosya_adi=None):
        """Bar chart çizer ve isteğe bağlı olarak dosyaya kaydeder"""
        try:
            plt.figure(figsize=(12, 7))
            x_pos = range(len(df))
            
            bar_width = 0.35
            bars1 = plt.bar([x - bar_width/2 for x in x_pos], df[y_col1], 
                           bar_width, label="Alış Değeri", color="lightcoral", alpha=0.8)
            bars2 = plt.bar([x + bar_width/2 for x in x_pos], df[y_col2], 
                           bar_width, label="Güncel Değer", color="lightgreen", alpha=0.8)
            
            # Değer etiketleri ekle
            for i, (bar1, bar2) in enumerate(zip(bars1, bars2)):
                y1_val = float(df[y_col1].iloc[i])
                y2_val = float(df[y_col2].iloc[i])
                kar_zarar = y2_val - y1_val
                yuzde = float(df["yuzde"].iloc[i])
                
                # Bar üstüne bilgi yaz
                max_height = max(y1_val, y2_val)
                plt.text(i, max_height * 1.05, 
                        f"{kar_zarar:+,.0f} TL\n(%{yuzde:+.1f})",
                        ha="center", va="bottom", fontsize=9,
                        color="green" if kar_zarar >= 0 else "red",
                        weight="bold")
            
            plt.xlabel("Varlık")
            plt.ylabel("Tutar (TL)")
            plt.title(title, fontsize=14, weight="bold")
            plt.xticks(x_pos, df[x_col], rotation=45 if len(df) > 5 else 0)
            plt.legend()
            plt.grid(True, linestyle="--", alpha=0.3)
            plt.tight_layout()
            
            if dosya_adi:
                plt.savefig(dosya_adi, dpi=300, bbox_inches='tight')
                logger.info(f"Grafik kaydedildi: {dosya_adi}")
            
            # Eğer GUI ortamında değilsek grafiği gösterme
            try:
                plt.show()
            except:
                logger.info("Grafik GUI'de gösterilemedi, dosya olarak kaydedildi")
            
            plt.close()
            
        except Exception as e:
            logger.error(f"Grafik çizimi hatası: {e}")

    try:
        # Ana işlem
        logger.info("Portföy raporu oluşturuluyor...")
        altin_df, hisse_df = portfoy_df_olustur(data)

        # Toplam hesaplamalar
        altin_toplam_deger = float(altin_df["toplam_guncel"].sum())
        altin_toplam_kz = float(altin_df["kar_zarar"].sum())
        altin_toplam_alis = float(altin_df["toplam_alis"].sum())
        altin_kz_oran = (altin_toplam_kz / altin_toplam_alis * 100) if altin_toplam_alis > 0 else 0.0

        hisse_toplam_deger = float(hisse_df["toplam_guncel"].sum())
        hisse_toplam_kz = float(hisse_df["kar_zarar"].sum())
        hisse_toplam_alis = float(hisse_df["toplam_alis"].sum())
        hisse_kz_oran = (hisse_toplam_kz / hisse_toplam_alis * 100) if hisse_toplam_alis > 0 else 0.0

        genel_toplam_deger = altin_toplam_deger + hisse_toplam_deger
        genel_toplam_kz = altin_toplam_kz + hisse_toplam_kz
        toplam_alis_tum = altin_toplam_alis + hisse_toplam_alis
        genel_kz_oran = (genel_toplam_kz / toplam_alis_tum * 100) if toplam_alis_tum > 0 else 0.0

        # Rapor metni oluştur - emoji'leri kaldır
        from datetime import datetime
        tarih = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        rapor_satirlari = [
            f"PORTFOY RAPORU - {tarih}",
            "=" * 60,
            "",
            "ALTIN YATIRIMLARI",
            "-" * 30
        ]
        
        # Altın tablosu
        for _, row in altin_df.iterrows():
            rapor_satirlari.append(
                f"{row['banka']:>10} | {row['adet']:>6.1f} gr | "
                f"Alış: {row['alis_fiyati']:>8.2f} | Güncel: {row['guncel_fiyat']:>8.2f} | "
                f"Toplam: {row['toplam_guncel']:>10,.0f} TL | "
                f"K/Z: {row['kar_zarar']:>+8,.0f} TL ({row['yuzde']:>+6.2f}%)"
            )
        
        rapor_satirlari.extend([
            "-" * 30,
            f"ALTIN TOPLAM: {altin_toplam_deger:,.0f} TL | K/Z: {altin_toplam_kz:+,.0f} TL ({altin_kz_oran:+.2f}%)",
            "",
            "HISSE YATIRIMLARI",
            "-" * 30
        ])
        
        # Hisse tablosu
        for _, row in hisse_df.iterrows():
            rapor_satirlari.append(
                f"{row['kod']:>6} | {row['adet']:>4.0f} adet | "
                f"Alış: {row['alis_fiyati']:>7.2f} | Güncel: {row['guncel_fiyat']:>7.2f} | "
                f"Toplam: {row['toplam_guncel']:>10,.0f} TL | "
                f"K/Z: {row['kar_zarar']:>+8,.0f} TL ({row['yuzde']:>+6.2f}%)"
            )
        
        rapor_satirlari.extend([
            "-" * 30,
            f"HISSE TOPLAM: {hisse_toplam_deger:,.0f} TL | K/Z: {hisse_toplam_kz:+,.0f} TL ({hisse_kz_oran:+.2f}%)",
            "",
            "GENEL OZET",
            "=" * 60,
            f"TOPLAM PORTFOY DEGERI: {genel_toplam_deger:,.0f} TL",
            f"GENEL KAR/ZARAR: {genel_toplam_kz:+,.0f} TL ({genel_kz_oran:+.2f}%)",
            "",
            f"Altin Agirligi: %{(altin_toplam_deger/genel_toplam_deger*100):.1f}",
            f"Hisse Agirligi: %{(hisse_toplam_deger/genel_toplam_deger*100):.1f}",
            "=" * 60
        ])

        rapor_metni = "\n".join(rapor_satirlari)
        
        # Grafikleri çiz (opsiyonel)
        try:
            if len(altin_df) > 0:
                grafik_ciz(altin_df, "banka", "toplam_alis", "toplam_guncel", 
                          "Altın Yatırım Performansı", "altin_grafik.png")
            
            if len(hisse_df) > 0:
                grafik_ciz(hisse_df, "kod", "toplam_alis", "toplam_guncel", 
                          "Hisse Yatırım Performansı", "hisse_grafik.png")
        except Exception as e:
            logger.error(f"Grafik oluşturma hatası: {e}")

        logger.info("Portföy raporu başarıyla oluşturuldu")
        return rapor_metni

    except Exception as e:
        logger.error(f"Portföy raporu oluşturma hatası: {e}")
        return f"HATA: Portföy raporu oluşturulamadı - {str(e)}"


def mail_gonder(icerik):
    """Raporu e-posta ile gönderir"""
    try:
        if not isinstance(icerik, str) or not icerik.strip():
            raise ValueError("Boş veya geçersiz rapor içeriği")

        # E-posta ayarları - Direkt kodda tanımlandı
        from_addr = "sefasmt@gmail.com"
        to_addr = "sefasmt@gmail.com" 
        app_pass = "qtab ikxe ytrf dtre"

        # E-posta oluştur
        msg = MIMEText(icerik, "plain", "utf-8")
        msg["Subject"] = f"Gunluk Portfoy Raporu - {pd.Timestamp.now().strftime('%d.%m.%Y')}"
        msg["From"] = from_addr
        msg["To"] = to_addr

        # Gmail SMTP ile gönder
        logger.info("E-posta gönderiliyor...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(from_addr, app_pass)
            server.send_message(msg)
            
        logger.info(f"E-posta basariyla gonderildi: {to_addr}")
        
    except Exception as e:
        logger.error(f"E-posta gonderme hatasi: {e}")
        raise


def main():
    """Ana fonksiyon"""
    try:
        # Rapor oluştur
        rapor = portfoy_raporu()
        
        # Konsola yazdır
        print("\n" + "="*80)
        print(rapor)
        print("="*80)
        
        # E-posta gönder
        mail_gonder(rapor)
        
        logger.info("Islem tamamlandi!")
        
    except Exception as e:
        logger.error(f"Ana program hatasi: {e}")
        print(f"\nHATA: {e}")


if __name__ == "__main__":
    main()